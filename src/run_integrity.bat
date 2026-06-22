@echo off
REM Re-hash periodico de integridad de los E-14. Detecta republicaciones/altas/bajas.
cd /d D:\ProyectosConIA\TransaparenciaVotaciones
echo ==== %DATE% %TIME% ==== >> data\e14\integrity\run.log
C:\Python313\python.exe execution\e14_auditor.py integrity >> data\e14\integrity\run.log 2>&1
