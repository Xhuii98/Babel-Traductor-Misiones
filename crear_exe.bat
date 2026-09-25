@echo off
cd /d "%~dp0"
echo Instalando dependencias...
python -m pip install -U -r requirements.txt pyinstaller
if errorlevel 1 goto error
echo.
echo Creando la version portable...
python -m PyInstaller --noconfirm --clean --onedir --windowed --noupx ^
  --name "Babel" ^
  --icon "icono.ico" ^
  --add-data "icono.ico;." ^
  --add-data "icono.png;." ^
  --version-file "version_info.txt" ^
  --collect-all customtkinter ^
  Babel.py
if errorlevel 1 goto error
echo.
echo Empaquetando en ZIP...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Babel' -DestinationPath 'dist\Babel_portable.zip' -Force"
echo.
echo Listo. La version portable esta en dist\Babel_portable.zip
pause
exit /b 0
:error
echo.
echo Algo fallo. Revisa el mensaje de arriba.
pause
exit /b 1
