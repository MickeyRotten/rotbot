@echo off
:::
:::        .n                   .                 .                  n.
:::  .   .dP                  dP                   9b                 9b.    .
::: 4    qXb         .       dX                     Xb       .        dXp     t
:::dX.    9Xb      .dXb    __                         __    dXb.     dXP     .Xb
:::9XXb._       _.dXXXXb dXXXXbo.                 .odXXXXb dXXXXb._       _.dXXP
::: 9XXXXXXXXXXXXXXXXXXXVXXXXXXXXOo.           .oOXXXXXXXXVXXXXXXXXXXXXXXXXXXXP
:::  `9XXXXXXXXXXXXXXXXXXXXX'~   ~`OOO8b   d8OOO'~   ~`XXXXXXXXXXXXXXXXXXXXXP'
:::    `9XXXXXXXXXXXP' `9XX'   DIE    `98v8P'  HUMAN   `XXP' `9XXXXXXXXXXXP'
:::        ~~~~~~~       9X.          .db|db.          .XP       ~~~~~~~
:::                        )b.  .dbo.dP'`v'`9b.odb.  .dX(
:::                      ,dXXXXXXXXXXXb     dXXXXXXXXXXXb.
:::                     dXXXXXXXXXXXP'   .   `9XXXXXXXXXXXb
:::                    dXXXXXXXXXXXXb   d|b   dXXXXXXXXXXXXb
:::                    9XXb'   `XXXXXb.dX|Xb.dXXXXX'   `dXXP
:::                     `'      9XXXXXX(   )XXXXXXP      `'
:::                              XXXX X.`v'.X XXXX
:::                              XP^X'`b   d'`X^XX
:::                              X. 9  `   '  P )X
:::                              `b  `       '  d'
:::                               `             '
:::
for /f "delims=: tokens=*" %%A in ('findstr /b ::: "%~f0"') do @echo(%%A
color 5E
rem 1) ensure Python 3.11 installed system-wide (quiet mode)
python --version >nul 2>&1
IF ERRORLEVEL 1 (
  echo Installing Python...
  powershell -NoProfile -Command ^
    "iwr https://www.python.org/ftp/python/3.11.4/python-3.11.4-amd64.exe -OutFile $env:TEMP\py-inst.exe"
  %TEMP%\py-inst.exe /quiet InstallAllUsers=1 PrependPath=1
)

rem 2) upgrade pip + core wheels (twitch & friends)
python -m pip install --upgrade pip
python -m pip install twitchio twitchAPI requests

echo Setup complete.  Double-click launch_bot.bat next time.
pause
