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
REM ──────────────────────────────────────────────────────────────
REM  reset_auth.bat
REM  Removes OAuth secrets for a clean re-authorisation.
REM  • Assumes this .bat sits in the liljuicerbot root folder
REM    which contains:  config.json   and   addons\ljb_* folders
REM ──────────────────────────────────────────────────────────────

REM 1) resolve base dir = folder that contains this script
set "BASE=%~dp0"
REM strip trailing backslash (Py-friendly)
if "%BASE:~-1%"=="\" set "BASE=%BASE:~0,-1%"

echo.
echo Wiping credentials under:
echo    %BASE%
echo.

REM 2) delete core config.json
if exist "%BASE%\config.json" (
    del "%BASE%\config.json"
    echo   - config.json removed
) else (
    echo   - no config.json found
)

REM 3) delete every addon_tokens.json (addons\ljb_*\addon_tokens.json)
for /f "delims=" %%F in ('dir "%BASE%\addons\ljb_*" /b /ad 2^>nul') do (
    if exist "%BASE%\addons\%%F\addon_tokens.json" (
        del "%BASE%\addons\%%F\addon_tokens.json"
        echo   - removed addons\%%F\addon_tokens.json
    )
)

echo.
echo Done. Launch the bot again to re-authorise Twitch & Spotify.
pause
