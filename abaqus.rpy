# -*- coding: mbcs -*-
#
# Abaqus/CAE Release 2022 replay file
# Internal Version: 2021_09_15-19.57.30 176069
# Run by keag on Fri Aug 28 14:06:19 2026
#

# from driverUtils import executeOnCaeGraphicsStartup
# executeOnCaeGraphicsStartup()
#: Executing "onCaeGraphicsStartup()" in the site directory ...
from abaqus import *
from abaqusConstants import *
session.Viewport(name='Viewport: 1', origin=(1.35156, 1.35), width=198.95, 
    height=133.92)
session.viewports['Viewport: 1'].makeCurrent()
from driverUtils import executeOnCaeStartup
executeOnCaeStartup()
execfile('build_parametric_model.py', __main__.__dict__)
#: [params] loaded from C:\simulations\D40_HEX_CONICAL_KRESINSKY_V1\parametric_builder\params.json
#* TypeError: name; found 'unicode', expecting a recognized type filling string 
#* dict
#* File "build_parametric_model.py", line 584, in <module>
#*     main()
#* File "build_parametric_model.py", line 563, in main
#*     m, report = build_all(params)
#* File "build_parametric_model.py", line 431, in build_all
#*     m = mdb.Model(name=name)
