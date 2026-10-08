using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public class TeaHostBudgetResult {
 public bool Started, TimedOut, PipeTimedOut, ReadFailed, Truncated, KillFailed;
 public bool ProcessExited, OutputComplete, CleanupAttempted, CleanupIncomplete, JobAssigned;
 public int? ExitCode, NativeErrorCode, ExceptionHResult;
 public int OutputLines, ErrorLines, BudgetMs, ExecutionBudgetMs, StdoutReadError, StderrReadError;
 public uint? RemainingOwnedProcesses;
 public double ElapsedMs;
 public string Stdout="", Stderr="", ExceptionType="", Status="NOT_STARTED";
 public string ImplementationVersion="monotonic-job-budget-v2-wsl-arguments-v4";
}

// Suspend root, assign to a private job, then resume. No descendants run before
// assignment, and cleanup never discovers or kills by process name/recycled PID.
public static class TeaHostNativeBudget2 {
 const uint INHERIT=1, CREATE_SUSPENDED=4, CREATE_NO_WINDOW=0x08000000, EXTENDED_STARTUP=0x80000;
 const uint KILL_ON_JOB_CLOSE=0x2000, GENERIC_READ=0x80000000, WAIT_OBJECT_0=0;
 static readonly IntPtr Invalid=new IntPtr(-1);
 [StructLayout(LayoutKind.Sequential)] struct Security { public int length; public IntPtr descriptor; public int inherit; }
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {
  public int cb; public string reserved,desktop,title;
  public uint x,y,xSize,ySize,xChars,yChars,fill,flags;
  public ushort show,reserved2; public IntPtr bytes,stdin,stdout,stderr;
 }
 [StructLayout(LayoutKind.Sequential)] struct StartupEx { public Startup startup; public IntPtr attributes; }
 [StructLayout(LayoutKind.Sequential)] struct ProcessInfo { public IntPtr process,thread; public uint pid,tid; }
 [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
  public long processTime,jobTime; public uint flags; public UIntPtr minWorking,maxWorking;
  public uint activeLimit; public UIntPtr affinity; public uint priority,scheduling;
 }
 [StructLayout(LayoutKind.Sequential)] struct IoCounters { public ulong a,b,c,d,e,f; }
 [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
  public BasicLimits basic; public IoCounters io; public UIntPtr processMemory,jobMemory,peakProcess,peakJob;
 }
 [StructLayout(LayoutKind.Sequential)] struct Accounting {
  public long user,kernel,periodUser,periodKernel; public uint faults,total,active,terminated;
 }
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref Security security,uint size);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetHandleInformation(IntPtr h,uint mask,uint flags);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFile(string name,uint access,uint share,ref Security security,uint disposition,uint flags,IntPtr template);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr security,string name);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int kind,ref ExtendedLimits limits,uint size);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int kind,out Accounting value,uint size,IntPtr returned);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateJobObject(IntPtr job,uint code);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string application,StringBuilder command,IntPtr processSecurity,IntPtr threadSecurity,bool inherit,uint flags,IntPtr environment,string cwd,ref StartupEx startup,out ProcessInfo info);
 [DllImport("kernel32.dll",SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
 [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr h,uint milliseconds);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,uint flags,ref IntPtr size);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr size,IntPtr previous,IntPtr returned);
 [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr list);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadFile(IntPtr h,byte[] data,uint length,out uint read,IntPtr overlapped);
 [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
 [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr OpenThread(uint access,bool inherit,uint tid);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool CancelSynchronousIo(IntPtr thread);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr h);

 // Dedicated background reader, no caller joins or blocking stream disposal.
 // Append-only published bytes support a lock-free partial snapshot.
 sealed class PipeReader {
  readonly byte[] saved; IntPtr handle; int used,done,error,lines,truncated,cancelFailed,cancelled; uint threadId;
  public PipeReader(IntPtr h,int cap) {handle=h;saved=new byte[cap];}
  public bool Done {get{return Volatile.Read(ref done)!=0;}}
  public int Error {get{return Volatile.Read(ref error);}}
  public bool Truncated {get{return Volatile.Read(ref truncated)!=0;}}
  public int Lines {get{return Volatile.Read(ref lines);}}
  public bool CancelFailed {get{return Volatile.Read(ref cancelFailed)!=0;}}
  public void Start() {
   try {var t=new Thread(Read);t.IsBackground=true;t.Start();}
   catch {CloseHandle(handle);handle=IntPtr.Zero;Volatile.Write(ref error,-1);Volatile.Write(ref done,1);throw;}
  }
  void Read() {
   threadId=GetCurrentThreadId();var buffer=new byte[1024];
   try {
    while(Volatile.Read(ref cancelled)==0) {
     uint n;
     if(!ReadFile(handle,buffer,(uint)buffer.Length,out n,IntPtr.Zero)) {
      int e=Marshal.GetLastWin32Error();if(e!=109 && e!=995)Volatile.Write(ref error,e);break;
     }
     if(n==0)break;
     for(int i=0;i<n;i++)if(buffer[i]==10)Interlocked.Increment(ref lines);
     int count=Math.Min((int)n,saved.Length-used);
     if(count>0) {Array.Copy(buffer,0,saved,used,count);Volatile.Write(ref used,used+count);}
     if(count<n)Volatile.Write(ref truncated,1);
    }
   } catch(Exception) {Volatile.Write(ref error,-1);}
   finally {CloseHandle(handle);handle=IntPtr.Zero;Volatile.Write(ref done,1);}
  }
  public void Cancel() {
   Interlocked.Exchange(ref cancelled,1);
   if(Done)return;uint id=threadId;
   if(id==0) {Volatile.Write(ref cancelFailed,1);return;}
   IntPtr t=OpenThread(1,false,id);
   if(t==IntPtr.Zero) {if(!Done)Volatile.Write(ref cancelFailed,1);return;}
   try {if(!CancelSynchronousIo(t) && Marshal.GetLastWin32Error()!=1168 && !Done)Volatile.Write(ref cancelFailed,1);}
   finally {CloseHandle(t);}
  }
  public string Snapshot() {return Encoding.UTF8.GetString(saved,0,Volatile.Read(ref used));}
 }
 public static string Quote(string s) {
  // WSL parses Windows options before forwarding the Linux command. Quoting
  // a simple option such as -d makes it a Linux command on this WSL version.
  // Quote only when required; retain CRT escaping for spaces, quotes and empty args.
  bool required=s.Length==0;
  foreach(char c in s)if(Char.IsWhiteSpace(c)||c=='"') {required=true;break;}
  if(!required)return s;
  var b=new StringBuilder("\"");int n=0;
  foreach(char c in s) {
   if(c=='\\') {n++;continue;}
   if(c=='"') {b.Append('\\',2*n+1);b.Append(c);n=0;continue;}
   b.Append('\\',n);n=0;b.Append(c);
  }
  b.Append('\\',2*n);b.Append('"');return b.ToString();
 }
 static void Check(bool ok) {if(!ok)throw new Win32Exception(Marshal.GetLastWin32Error());}
 static void Close(ref IntPtr h) {if(h!=IntPtr.Zero && h!=Invalid)CloseHandle(h);h=IntPtr.Zero;}
 static int Left(Stopwatch clock,int deadline) {return Math.Max(0,deadline-(int)clock.ElapsedMilliseconds);}
 static bool Exited(IntPtr p) {return p!=IntPtr.Zero && WaitForSingleObject(p,0)==WAIT_OBJECT_0;}
 static uint? Active(IntPtr job) {
  Accounting a;return QueryInformationJobObject(job,1,out a,(uint)Marshal.SizeOf(typeof(Accounting)),IntPtr.Zero)?(uint?)a.active:null;
 }
 public static TeaHostBudgetResult Run(string exe,string[] args,int timeoutMs,int cap) {
  var clock=Stopwatch.StartNew();var r=new TeaHostBudgetResult();r.BudgetMs=Math.Max(0,timeoutMs);
  // Reserve at most200ms WITHIN the caller's total budget for owned-tree cleanup.
  int reserve=Math.Min(200,Math.Max(1,r.BudgetMs/4));r.ExecutionBudgetMs=Math.Max(0,r.BudgetMs-reserve);
  IntPtr job=IntPtr.Zero,rdOut=IntPtr.Zero,wrOut=IntPtr.Zero,rdErr=IntPtr.Zero,wrErr=IntPtr.Zero,stdin=IntPtr.Zero;
  IntPtr attrs=IntPtr.Zero,handles=IntPtr.Zero;bool initialized=false,readStarted=false;
  ProcessInfo pi=new ProcessInfo();PipeReader stdout=null,stderr=null;
  try {
   if(r.BudgetMs<=0) {r.TimedOut=true;r.Status="PROCESS_TIMEOUT";return r;}
   job=CreateJobObject(IntPtr.Zero,null);Check(job!=IntPtr.Zero);
   var limits=new ExtendedLimits();limits.basic.flags=KILL_ON_JOB_CLOSE;
   Check(SetInformationJobObject(job,9,ref limits,(uint)Marshal.SizeOf(typeof(ExtendedLimits))));
   var security=new Security {length=Marshal.SizeOf(typeof(Security)),inherit=1};
   Check(CreatePipe(out rdOut,out wrOut,ref security,0));Check(SetHandleInformation(rdOut,INHERIT,0));
   Check(CreatePipe(out rdErr,out wrErr,ref security,0));Check(SetHandleInformation(rdErr,INHERIT,0));
   stdin=CreateFile("NUL",GENERIC_READ,3,ref security,3,0,IntPtr.Zero);Check(stdin!=Invalid);
   var startup=new StartupEx();startup.startup.cb=Marshal.SizeOf(typeof(StartupEx));startup.startup.flags=0x101;
   startup.startup.stdin=stdin;startup.startup.stdout=wrOut;startup.startup.stderr=wrErr;
   IntPtr size=IntPtr.Zero;InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);
   attrs=Marshal.AllocHGlobal(size);Check(InitializeProcThreadAttributeList(attrs,1,0,ref size));initialized=true;
   handles=Marshal.AllocHGlobal(IntPtr.Size*3);
   Marshal.WriteIntPtr(handles,0,stdin);Marshal.WriteIntPtr(handles,IntPtr.Size,wrOut);Marshal.WriteIntPtr(handles,IntPtr.Size*2,wrErr);
   Check(UpdateProcThreadAttribute(attrs,0,new IntPtr(0x20002),handles,new IntPtr(IntPtr.Size*3),IntPtr.Zero,IntPtr.Zero));startup.attributes=attrs;
   if(Left(clock,r.ExecutionBudgetMs)==0) {r.TimedOut=true;r.Status="PROCESS_TIMEOUT";}
   else {
    var command=new StringBuilder(Quote(exe));foreach(string a in args)command.Append(" ").Append(Quote(a));
    Check(CreateProcess(exe,command,IntPtr.Zero,IntPtr.Zero,true,CREATE_SUSPENDED|CREATE_NO_WINDOW|EXTENDED_STARTUP,IntPtr.Zero,null,ref startup,out pi));r.Started=true;
    Check(AssignProcessToJobObject(job,pi.process));r.JobAssigned=true;
    stdout=new PipeReader(rdOut,cap);rdOut=IntPtr.Zero;stderr=new PipeReader(rdErr,cap);rdErr=IntPtr.Zero;
    readStarted=true;stdout.Start();stderr.Start();Check(ResumeThread(pi.thread)!=UInt32.MaxValue);
   }
   Close(ref wrOut);Close(ref wrErr);Close(ref stdin);
   if(r.Started) {
    while(Left(clock,r.ExecutionBudgetMs)>0) {
     r.ProcessExited=Exited(pi.process);
     if(stdout.Error!=0 || stderr.Error!=0) {r.ReadFailed=true;r.Status="OUTPUT_READ_FAILED";break;}
     if(r.ProcessExited && stdout.Done && stderr.Done) {r.Status="COMPLETE";break;}
     Thread.Sleep(Math.Min(5,Left(clock,r.ExecutionBudgetMs)));
    }
    r.ProcessExited=Exited(pi.process);
    if(r.Status!="COMPLETE" && !r.ReadFailed) {
     if(!r.ProcessExited) {r.TimedOut=true;r.Status="PROCESS_TIMEOUT";}
     else {r.PipeTimedOut=true;r.Status="PIPE_NOT_CLOSED";}
    }
   }
  } catch(Exception e) {
   r.ExceptionType=e.GetType().FullName;r.ExceptionHResult=e.HResult;
   var native=e as Win32Exception;if(native!=null)r.NativeErrorCode=native.NativeErrorCode;
   r.Status=r.Started?(r.JobAssigned?"PROCESS_SETUP_FAILED":"OWNERSHIP_SETUP_FAILED"):"PROCESS_START_FAILED";
  } finally {
   Close(ref wrOut);Close(ref wrErr);Close(ref stdin);
   if(pi.process!=IntPtr.Zero) {
    uint? active=r.JobAssigned?Active(job):(uint?)(Exited(pi.process)?0:1);
    bool readersDone=!readStarted || (stdout.Done && stderr.Done);
    if(active!=0 || !readersDone) {
     r.CleanupAttempted=true;
     bool killed=r.JobAssigned?TerminateJobObject(job,1460):TerminateProcess(pi.process,1460);
     if(!killed)r.KillFailed=true;
     // Only zero-length polls and sleeps clipped to the SAME remaining budget.
     while(Left(clock,r.BudgetMs)>0) {
      active=r.JobAssigned?Active(job):(uint?)(Exited(pi.process)?0:1);
      readersDone=!readStarted || (stdout.Done && stderr.Done);
      if(active==0 && readersDone)break;
      Thread.Sleep(Math.Min(5,Left(clock,r.BudgetMs)));
     }
     if(readStarted) {stdout.Cancel();stderr.Cancel();}
    }
    r.ProcessExited=Exited(pi.process);
    uint exit;if(r.ProcessExited && GetExitCodeProcess(pi.process,out exit))r.ExitCode=unchecked((int)exit);
    r.RemainingOwnedProcesses=r.JobAssigned?Active(job):(uint?)(r.ProcessExited?0:1);
    r.CleanupIncomplete=r.KillFailed || r.RemainingOwnedProcesses!=0 || (readStarted && (!stdout.Done || !stderr.Done || stdout.CancelFailed || stderr.CancelFailed));
   }
   if(stdout!=null) {r.Stdout=stdout.Snapshot();r.OutputLines=stdout.Lines;r.StdoutReadError=stdout.Error;r.Truncated=stdout.Truncated;}
   if(stderr!=null) {r.Stderr=stderr.Snapshot();r.ErrorLines=stderr.Lines;r.StderrReadError=stderr.Error;r.Truncated|=stderr.Truncated;}
   r.ReadFailed|=r.StdoutReadError!=0 || r.StderrReadError!=0;
   r.OutputComplete=readStarted && stdout.Done && stderr.Done && !r.Truncated && !r.TimedOut && !r.PipeTimedOut && !r.ReadFailed && !r.CleanupIncomplete && r.ExceptionType=="";
   if(r.ReadFailed && r.Status=="COMPLETE")r.Status="OUTPUT_READ_FAILED";
   // Job close also terminates only its owned descendants if verification exhausted the budget.
   Close(ref job);Close(ref pi.thread);Close(ref pi.process);Close(ref rdOut);Close(ref rdErr);
   if(initialized)DeleteProcThreadAttributeList(attrs);
   if(attrs!=IntPtr.Zero)Marshal.FreeHGlobal(attrs);if(handles!=IntPtr.Zero)Marshal.FreeHGlobal(handles);
   r.ElapsedMs=clock.Elapsed.TotalMilliseconds;
  }
  return r;
 }
}
