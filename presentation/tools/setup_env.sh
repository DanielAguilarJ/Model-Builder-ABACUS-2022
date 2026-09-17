#!/bin/sh
# Restore the toolchain this sandbox loses between calls.
# Anything under /projects persists; system packages and pip installs do not.
set -e

dnf install -y python3-tkinter ImageMagick xorg-x11-server-Xvfb \
    liberation-fonts liberation-sans-fonts liberation-mono-fonts \
    dejavu-sans-fonts >/tmp/setup_dnf.log 2>&1 || true

/usr/bin/python3 -m pip install --quiet python-pptx matplotlib pillow \
    >/tmp/setup_pip.log 2>&1

cat > /etc/fonts/local.conf <<'CONF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <alias binding="strong"><family>Segoe UI</family>
    <prefer><family>Liberation Sans</family><family>DejaVu Sans</family></prefer></alias>
  <alias binding="strong"><family>Segoe UI Semibold</family>
    <prefer><family>Liberation Sans</family><family>DejaVu Sans</family></prefer></alias>
  <alias binding="strong"><family>Consolas</family>
    <prefer><family>Liberation Mono</family><family>DejaVu Sans Mono</family></prefer></alias>
</fontconfig>
CONF
fc-cache -f >/dev/null 2>&1

/usr/bin/python3 -c "import pptx, matplotlib, PIL, tkinter; \
print('env ready: pptx', pptx.__version__, '| mpl', matplotlib.__version__, \
'| PIL', PIL.__version__)"
command -v convert >/dev/null || { echo 'convert MISSING'; exit 1; }
