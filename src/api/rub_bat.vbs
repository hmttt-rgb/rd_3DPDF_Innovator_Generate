Set WshShell = CreateObject("WScript.Shell")

'0 = Hide the window
WshShell.Run chr(34) & "C:\3DPDF\99_3DPDF_generate\api\start_api.bat" & chr(34), 0

Set WshShell = Nothing