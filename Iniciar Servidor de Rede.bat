@echo off
title Sistema de Contratos - SERVIDOR DE REDE (nao feche esta janela)
cd /d "%~dp0"

rem Libera a porta 8765 no Firewall do Windows (pede permissao de administrador so na primeira vez)
netsh advfirewall firewall show rule name="Sistema de Contratos Demo" >nul 2>nul
if errorlevel 1 (
    echo Liberando a porta 8765 no Firewall do Windows...
    powershell -NoProfile -Command "Start-Process netsh -Verb RunAs -Wait -ArgumentList 'advfirewall firewall add rule name=\"Sistema de Contratos Demo\" dir=in action=allow protocol=TCP localport=8765 profile=domain,private'"
)

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  Python nao foi encontrado neste computador.
        echo  Instale o Python 3 em https://www.python.org/downloads/
        echo  marcando a opcao "Add Python to PATH".
        echo.
        pause
        exit /b 1
    )
    py -3 servidor.py --rede
    goto fim
)
python servidor.py --rede

:fim
echo.
echo  O servidor foi encerrado. Os outros computadores perderam o acesso.
pause
