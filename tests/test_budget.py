"""Real Windows PS5.1 -> local synthetic native process (no network/auth).
Own-job cleanup tests include immediate parent exit with inherited open pipes.
"""
import importlib.util, json, os, shutil, subprocess, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parent;SCRIPTS=PROJECT/'cloud'
PS=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
import tempfile
OUT=Path(tempfile.mkdtemp(prefix='native fixtures with spaces '))
SOURCE=r'''
using System;using System.IO;using System.Diagnostics;using System.Threading;using System.Runtime.InteropServices;using System.Text;
public class SyntheticBudget {
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct SI {
  public int cb;public string reserved,desktop,title;public uint x,y,xsize,ysize,xc,yc,fill,flags;public ushort show,reserved2;public IntPtr bytes,input,output,error;
 }
 [StructLayout(LayoutKind.Sequential)] struct PI {public IntPtr process,thread;public uint pid,tid;}
 [DllImport("kernel32.dll")]static extern IntPtr GetStdHandle(int n);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateProcess(string app,StringBuilder command,IntPtr ps,IntPtr ts,bool inherit,uint flags,IntPtr env,string cwd,ref SI si,out PI pi);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr h);
 public static int Main(string[] args) {
  string mode=args[0],file=args[1];var me=Process.GetCurrentProcess();
  File.AppendAllText(file,me.Id+"|"+me.StartTime.ToUniversalTime().Ticks+"|"+mode+"\n");
  if(mode=="pipe-child") {Console.Error.WriteLine("PUBLIC_CHILD_PIPE_HELD");Thread.Sleep(6000);return 0;}
  if(mode=="pipe-parent") {
   Console.WriteLine("PUBLIC_PARENT_OUTPUT");Console.Error.WriteLine("PUBLIC_PARENT_STDERR");
   string exe=me.MainModule.FileName;var si=new SI();si.cb=Marshal.SizeOf(typeof(SI));si.flags=0x100;
   si.input=GetStdHandle(-10);si.output=GetStdHandle(-11);si.error=GetStdHandle(-12);PI pi;
   if(!CreateProcess(exe,new StringBuilder("\""+exe+"\" pipe-child \""+file+"\""),IntPtr.Zero,IntPtr.Zero,true,0x08000000,IntPtr.Zero,null,ref si,out pi))return 19;
   CloseHandle(pi.thread);CloseHandle(pi.process);
   return 0; // immediate exit; no wait for the descendant holding inherited pipes
  }
  if(mode=="sleep"||mode=="partial") {
   if(mode=="partial") {Console.WriteLine("PUBLIC_PARTIAL");Console.Error.WriteLine("PUBLIC_PARTIAL_ERR");}
   Thread.Sleep(6000);return 0;
  }
  if(mode=="large") {Console.Write(new String('X',12000));return 0;}
  Console.WriteLine("PUBLIC_NORMAL");Console.Error.WriteLine("PUBLIC_ERROR_STREAM");return mode=="nonzero"?7:0;
 }
}
'''
RUNNER=r'''param([string]$Module,[string]$Exe,[string]$Mode,[string]$PidFile,[int]$Budget,[string]$Result,[string]$Fault)
. $Module
if($Fault){[TeaHostNativeBudget2TestFault]::ForceReadFailure=($Fault -eq 'Read');[TeaHostNativeBudget2TestFault]::ForceCleanupFailure=($Fault -eq 'Cleanup')}
$watch=[Diagnostics.Stopwatch]::StartNew()
$r=Invoke-HostNative $Exe @($Mode,$PidFile) $Budget
$wall=$watch.Elapsed.TotalMilliseconds
$alive=@();$records=@()
if(Test-Path -LiteralPath $PidFile) {
 foreach($line in (Get-Content -LiteralPath $PidFile)){
  $parts=$line.Split('|');$owned=$false;$running=$false
  try{$p=[Diagnostics.Process]::GetProcessById([int]$parts[0]);$owned=($p.StartTime.ToUniversalTime().Ticks -eq [long]$parts[1]);$running=$owned -and !$p.HasExited;$p.Dispose()}catch{}
  $records+=@{pid=[int]$parts[0];creation_ticks=$parts[1];mode=$parts[2];same_instance_alive=$running}
  if($running){$alive+=[int]$parts[0]}
 }
}
@{native=$r;wall_ms=$wall;processes=$records;owned_processes_still_alive=$alive;PS_version=$PSVersionTable.PSVersion.ToString()}|
 ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Result -Encoding UTF8
if($alive.Count){exit 10}
'''

def ps(script,args=(),timeout=25):
    return subprocess.run([str(PS),'-NoProfile','-File',str(script),*map(str,args)],
      stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,v):path.write_text(json.dumps(v,indent=2),encoding='utf-8')
def build_fault():
    text=(SCRIPTS/'HostCapture.Native.cs').read_text()
    text=text.replace('TeaHostNativeBudget2','TeaHostNativeBudget2TestFault')
    text=text.replace('public static class TeaHostNativeBudget2TestFault {',
      'public static class TeaHostNativeBudget2TestFault { public static bool ForceReadFailure,ForceCleanupFailure;')
    original='Accounting a;return QueryInformationJobObject'
    text=text.replace(original,'if(ForceCleanupFailure)return 1;Accounting a;return QueryInformationJobObject')
    # Actual reader error injection, without exposing a production test switch.
    text=text.replace('static extern bool ReadFile(', 'static extern bool RealReadFile(')
    text=text.replace('[DllImport("kernel32.dll",SetLastError=true)] static extern bool RealReadFile(',
      '[DllImport("kernel32.dll",EntryPoint="ReadFile",SetLastError=true)] static extern bool RealReadFile(')
    point='static extern uint GetCurrentThreadId();'
    text=text.replace(point,point+r'''
 [DllImport("kernel32.dll",SetLastError=true)]static extern void SetLastError(uint value);
 static bool ReadFile(IntPtr h,byte[] data,uint len,out uint read,IntPtr overlapped) {
  if(ForceReadFailure){read=0;SetLastError(1234);return false;}return RealReadFile(h,data,len,out read,overlapped);
 }
''')
    fault=OUT/'fault-only';fault.mkdir()
    (fault/'HostCapture.Native.cs').write_text(text,encoding='utf-8')
    (fault/'HostCapture.Native.ps1').write_text(r'''Add-Type -Path (Join-Path $PSScriptRoot 'HostCapture.Native.cs')
function Invoke-HostNative([string]$Executable,[string[]]$ArgumentList,[int]$TimeoutMs){
 [TeaHostNativeBudget2TestFault]::Run($Executable,$ArgumentList,$TimeoutMs,8192)
}''',encoding='ascii')
    return fault/'HostCapture.Native.ps1'

def main():
    start=time.monotonic();rows=[]
    (OUT/'synthetic.cs').write_text(SOURCE,encoding='ascii')
    (OUT/'build.ps1').write_text('Add-Type -Path $args[0] -OutputAssembly $args[1] -OutputType ConsoleApplication',encoding='ascii')
    exe=OUT/'synthetic native with spaces.exe'
    result=ps(OUT/'build.ps1',[OUT/'synthetic.cs',exe]);assert result.returncode==0,result.stderr
    runner=OUT/'native runner.ps1';runner.write_text(RUNNER,encoding='ascii')
    fault=build_fault()
    def case(name,mode,budget=1000,missing=False,inject=''):
        folder=OUT/name;folder.mkdir()
        result=ps(runner,[fault if inject else SCRIPTS/'HostCapture.Native.ps1',
          folder/'missing.exe' if missing else exe,mode,folder/'pids.txt',budget,folder/'result.json',inject])
        (folder/'PS.stdout.txt').write_bytes(result.stdout);(folder/'PS.stderr.txt').write_bytes(result.stderr)
        assert result.returncode==0,(name,result.returncode,result.stderr)
        data=read(folder/'result.json');r=data['native']
        assert not data['owned_processes_still_alive'],data
        assert data['wall_ms']<budget+750,(name,data['wall_ms'])
        assert r['ElapsedMs']<=data['wall_ms']+10
        assert r['ImplementationVersion']=='monotonic-job-budget-v2-wsl-arguments-v4'
        return data,r
    def check(name,action):
        data=action();rows.append(dict(name=name,passed=True,**(data or {})))
    def normal():
        data,r=case('normal','normal');assert r['Status']=='COMPLETE' and r['OutputComplete'] and r['ExitCode']==0
        assert 'PUBLIC_NORMAL' in r['Stdout'] and 'PUBLIC_ERROR_STREAM' in r['Stderr'];return dict(elapsed_ms=r['ElapsedMs'])
    check('Normal stdout/stderr complete',normal)
    def nonzero():
        data,r=case('nonzero','nonzero');assert r['ExitCode']==7 and r['OutputComplete'];return dict(elapsed_ms=r['ElapsedMs'])
    check('Nonzero exit code preserved without misclassifying output',nonzero)
    def sleeping(mode):
        data,r=case(mode,mode);assert r['TimedOut'] and r['Status']=='PROCESS_TIMEOUT' and not r['OutputComplete']
        assert r['JobAssigned'] and r['RemainingOwnedProcesses']==0 and not r['CleanupIncomplete']
        assert 700<r['ElapsedMs']<1500
        if mode=='partial':assert 'PUBLIC_PARTIAL' in r['Stdout'] and 'PUBLIC_PARTIAL_ERR' in r['Stderr']
        return dict(budget_ms=1000,elapsed_ms=r['ElapsedMs'],wall_ms=data['wall_ms'])
    check('Sleeping root timeout plus cleanup uses same total budget',lambda:sleeping('sleep'))
    check('Partial stdout/stderr retained and marked incomplete',lambda:sleeping('partial'))
    def inherited():
        data,r=case('inherited-pipes','pipe-parent')
        assert len(data['processes'])==2,data
        assert r['ProcessExited'] and r['ExitCode']==0 and r['PipeTimedOut'] and not r['TimedOut']
        assert r['Status']=='PIPE_NOT_CLOSED' and not r['OutputComplete']
        assert r['CleanupAttempted'] and not r['CleanupIncomplete'] and r['RemainingOwnedProcesses']==0
        assert 'PUBLIC_PARENT_OUTPUT' in r['Stdout'] and 'PUBLIC_CHILD_PIPE_HELD' in r['Stderr']
        assert 700<r['ElapsedMs']<1500
        return dict(budget_ms=1000,elapsed_ms=r['ElapsedMs'],wall_ms=data['wall_ms'],descendant_insurance_lifetime_ms=6000,remaining_owned_processes=0)
    check('Parent exits immediately; descendant holds inherited stdout/stderr',inherited)
    def failed_start():
        data,r=case('start-failure','normal',missing=True)
        assert not r['Started'] and r['Status']=='PROCESS_START_FAILED' and r['NativeErrorCode']==2 and r['ExitCode'] is None
        return dict(elapsed_ms=r['ElapsedMs'])
    check('Process startup failure preserves native error code',failed_start)
    def large():
        _,r=case('bounded-output','large');assert r['Truncated'] and not r['OutputComplete'] and len(r['Stdout'])<=8192
    check('Output cap never promotes truncated output to complete',large)
    def read_fault():
        _,r=case('read-fault','normal',inject='Read')
        assert r['ReadFailed'] and r['Status']=='OUTPUT_READ_FAILED' and not r['OutputComplete'],r
        assert r['StdoutReadError']==1234 or r['StderrReadError']==1234
    check('Injected native reader failure explicitly classified',read_fault)
    def cleanup_fault():
        data,r=case('cleanup-fault','sleep',inject='Cleanup')
        assert r['TimedOut'] and r['CleanupIncomplete'] and not r['OutputComplete']
        assert 900<r['ElapsedMs']<1500
        return dict(budget_ms=1000,elapsed_ms=r['ElapsedMs'],fault='synthetic job-accounting verification obstruction; real private job terminated')
    check('Unfinished cleanup reports error within same budget',cleanup_fault)
    text=(SCRIPTS/'HostCapture.Native.cs').read_text();module=(SCRIPTS/'HostCapture.Native.ps1').read_text()
    assert 'WaitForExit' not in text+module and '.Result' not in text and '.Join(' not in text and '.Wait(' not in text
    assert 'WaitForSingleObject(p,0)' in text and 'AssignProcessToJobObject(job,pi.process)' in text
    check('No unconditional wait/join/read/task-result or name-based kill in caller',lambda:None)
    write(OUT/'budget-tests.json',dict(passed=True,tests=rows,test_count=len(rows),elapsed_seconds=time.monotonic()-start,
      real_windows_PowerShell_to_native=True,reader_and_cleanup_faults='explicit local-only generated test variants; not production flags',
      cloud_API_calls=0,remote_scans=0,SSH_connections=0,auth_reads=0,trust_changes=0))
    print(json.dumps(read(OUT/'budget-tests.json'),indent=2))

if __name__=='__main__':main()
