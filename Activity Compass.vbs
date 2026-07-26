Option Explicit

Dim shell, files, projectRoot, bundledPythonw, command

Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
projectRoot = files.GetParentFolderName(WScript.ScriptFullName)
bundledPythonw = shell.ExpandEnvironmentStrings( _
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe" _
)

If files.FileExists(bundledPythonw) Then
    command = Quote(bundledPythonw) & " " & Quote(projectRoot & "\launcher.pyw")
ElseIf files.FileExists(shell.ExpandEnvironmentStrings("%WINDIR%\pyw.exe")) Then
    command = Quote(shell.ExpandEnvironmentStrings("%WINDIR%\pyw.exe")) & _
        " -3 " & Quote(projectRoot & "\launcher.pyw")
Else
    MsgBox "Python 3 is required to start Activity Compass.", vbCritical, "Activity Compass"
    WScript.Quit 1
End If

' 0 = hidden window, False = return immediately after the GUI starts.
shell.Run command, 0, False

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function
