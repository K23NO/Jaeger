#!/bin/bash
# Deja una RPi recien grabada igual que la del proyecto (visión + UART al myRIO).
# Uso (desde la laptop, despues de copiarlo):
#   scp .\Project_ball\Raspberry-Pi3B\configurar_rpi.sh rpi-ballplate:~
#   ssh -t rpi-ballplate "bash ~/configurar_rpi.sh"
# Al final reinicia la RPi (para que tome la UART).
set -e

echo "=== 1/4 Actualizar e instalar paquetes ==="
sudo apt update
sudo apt full-upgrade -y
# OpenCV, numpy y pyserial de apt: ya vienen compilados para la RPi, sin venv.
sudo apt install -y python3-opencv python3-numpy python3-serial v4l-utils

echo "=== 2/4 UART en GPIO14/15 (pines 8 y 10) ==="
sudo raspi-config nonint do_serial_cons 1    # sin consola serie (la UART queda libre)
sudo raspi-config nonint do_serial_hw 0      # UART por hardware activada
# En la RPi 3 la UART buena (PL011) la usa el Bluetooth: se la quitamos.
if ! grep -q "^dtoverlay=disable-bt" /boot/firmware/config.txt; then
    echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
fi

echo "=== 3/4 Carpetas ==="
mkdir -p ~/pruebas ~/vision

echo "=== 4/4 Comprobaciones ==="
echo "Modelo:      $(tr -d '\0' < /proc/device-tree/model)"
echo "Energia:     $(vcgencmd get_throttled)   (debe ser 0x0)"
echo "Camara:      $(lsusb | grep -i brio || echo 'NO se ve la Brio')"
echo "Python:      $(python3 -c 'import cv2, numpy, serial; print("cv2", cv2.__version__, "| numpy", numpy.__version__, "| pyserial", serial.__version__)')"
echo "config.txt:  $(grep -E '^(enable_uart|dtoverlay=disable-bt)' /boot/firmware/config.txt | tr '\n' ' ')"
echo
echo "Listo. Reiniciando en 5 s para activar la UART (despues: ls -l /dev/serial0 -> ttyAMA0)"
sleep 5
sudo reboot
