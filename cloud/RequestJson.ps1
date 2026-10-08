function ConvertFrom-RequestJson([string]$Text) {
    # PS 7.5+ otherwise turns ISO UTC strings into DateTime and changes serialization.
    if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) {
        return ($Text | ConvertFrom-Json -DateKind String)
    }
    return ($Text | ConvertFrom-Json)
}
function ConvertFrom-JsonUtc {
    param([Parameter(ValueFromPipeline=$true)][string]$InputObject)
    process { ConvertFrom-RequestJson $InputObject }
}
