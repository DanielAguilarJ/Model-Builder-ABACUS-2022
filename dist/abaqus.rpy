# -*- coding: mbcs -*-
#
# Abaqus/CAE Release 2022 replay file
# Internal Version: 2021_09_15-19.57.30 176069
# Run by keag on Fri Aug 28 15:18:55 2026
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
execfile(
    'C:/simulations/D40_HEX_CONICAL_KRESINSKY_V1/parametric_builder/dist/build_parametric_model.py', 
    __main__.__dict__)
#: [params] loaded from C:\simulations\D40_HEX_CONICAL_KRESINSKY_V1\parametric_builder\dist\params.json
#: The model "PARAM_MODEL" has been created.
#: [build] shaft ...
#: [build] key ...
#: [build] bushing ...
#: Warning: One or more instances of this part exists in the
#: assembly. They have been modified to refer to the renamed part.
#: Any assembly features and attributes that depend on the original
#: instance may become invalid due to this operation. You may need
#: to edit assembly attributes, sets, surfaces, and reference points.
#: [build] hub ...
#: [mesh] shaft ...
#: [mesh] key ...
#: [mesh] bushing ...
#: [mesh] hub ...
#: The model database has been saved to "C:\simulations\D40_HEX_CONICAL_KRESINSKY_V1\parametric_builder\dist\PARAM_MODEL.cae".
#: [save] CAE written to C:\simulations\D40_HEX_CONICAL_KRESINSKY_V1\parametric_builder\dist\PARAM_MODEL.cae
#: PARAMETRIC BUILD AUDIT
#: model: PARAM_MODEL
#: element_order: quadratic
#: steps=['Initial'] jobs=[] constraints=[] interactions=[]
#: PART Shaft
#:    nodes=533784 elements=128100 types={'C3D20R': 126902, 'C3D10M': 1198}
#:    bbox_size=[50.0, 50.0, 120.0]
#:    failed=2 warnings=1947 aspectRatio worst=117.460159302 avg=1.60731434822 components=1
#: PART Key
#:    nodes=149202 elements=34602 types={'C3D20R': 34602}
#:    bbox_size=[12.0, 8.0, 38.0]
#:    failed=0 warnings=0 aspectRatio worst=3.0000231266 avg=1.13726627827 components=1
#: PART Bushing
#:    nodes=425487 elements=98658 types={'C3D20R': 98658}
#:    bbox_size=[63.8, 38.0, 63.8]
#:    failed=5 warnings=397 aspectRatio worst=5.03022480011 avg=1.247641325 components=1
#: PART Hub
#:    nodes=332420 elements=75240 types={'C3D20R': 75240}
#:    bbox_size=[80.0, 38.0, 80.0]
#:    failed=0 warnings=0 aspectRatio worst=1.29686486721 avg=1.1227697134 components=1
#: TOTAL nodes=1440893 elements=336600
#: SETS: ['ALL_BUSHING_ELEMENTS', 'ALL_BUSHING_NODES', 'ALL_HUB_ELEMENTS', 'ALL_HUB_NODES', 'ALL_KEY_ELEMENTS', 'ALL_KEY_NODES', 'ALL_SHAFT_ELEMENTS', 'ALL_SHAFT_NODES']
#: VERDICT: CHECK (a part failed or is disconnected)
#: NOTE: NOJOB model - no contact, step, load, BC or job defined.
#: [done] build finished, verdict OK = False
print 'RT script done'
#: RT script done
