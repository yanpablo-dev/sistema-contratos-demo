@echo off
title Sistema de Gestao de Contratos - Demo
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  Python nao foi encontrado neste computador.
        echo  Instale o Python 3 em https://www.python.org/downloads/
        echo  marcando a opcao "Add Python to PATH" e abra este arquivo de novo.
        echo.
        pause
        exit /b 1
    )
    py -3 servidor.py
    goto fim
)
python servidor.py

:fim
echo.
echo  O sistema foi encerrado.
pause
