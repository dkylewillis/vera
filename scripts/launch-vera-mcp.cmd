@echo off
setlocal EnableExtensions
rem Launch vera-mcp for Codex/ChatGPT plugin hosts that may lack the user PATH.

where vera-mcp >nul 2>&1
if %ERRORLEVEL%==0 (
  vera-mcp %*
  exit /b %ERRORLEVEL%
)

if exist "%USERPROFILE%\AppData\Roaming\Python\Python313\Scripts\vera-mcp.exe" (
  "%USERPROFILE%\AppData\Roaming\Python\Python313\Scripts\vera-mcp.exe" %*
  exit /b %ERRORLEVEL%
)

if exist "%USERPROFILE%\AppData\Roaming\Python\Python312\Scripts\vera-mcp.exe" (
  "%USERPROFILE%\AppData\Roaming\Python\Python312\Scripts\vera-mcp.exe" %*
  exit /b %ERRORLEVEL%
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\Scripts\vera-mcp.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python313\Scripts\vera-mcp.exe" %*
  exit /b %ERRORLEVEL%
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\Scripts\vera-mcp.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python312\Scripts\vera-mcp.exe" %*
  exit /b %ERRORLEVEL%
)

if exist "%ProgramFiles%\Python313\Scripts\vera-mcp.exe" (
  "%ProgramFiles%\Python313\Scripts\vera-mcp.exe" %*
  exit /b %ERRORLEVEL%
)

echo vera-mcp not found. Install with: python -m pip install "vera-mcp>=0.3.2,<0.4" 1>&2
exit /b 1
