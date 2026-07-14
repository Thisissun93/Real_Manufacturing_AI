PROCESS_SPEC = {
    "CZ_Concentration": {
        "equipment_min": 0.0,
        "equipment_max": 100.0,
        "lcl": 9.5,
        "target": 10.0,
        "ucl": 10.5,
        "unit": "%"
    },
    "CZ_Roughness": {
        "equipment_min": 0.0,
        "equipment_max": 1000.0,
        "lcl": 320.0,
        "target": 350.0,
        "ucl": 380.0,
        "unit": "um"
    },
    "Press1_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 200.0,
        "lcl": 97.0,
        "target": 100.0,
        "ucl": 103.0,
        "unit": "°C"
    },
    "Press1_Time": {
        "equipment_min": 15.0,
        "equipment_max": 45.0,
        "lcl": None,
        "target": 30.0,
        "ucl": None,
        "unit": "sec"
    },
    "Press1_Pressure": {
        "equipment_min": 0.0,
        "equipment_max": 10.0,
        "lcl": 4.0,
        "target": 5.0,
        "ucl": 6.0,
        "unit": "kgf/cm²"
    },
    "Press2_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 200.0,
        "lcl": 97.0,
        "target": 100.0,
        "ucl": 103.0,
        "unit": "°C"
    },
    "Press2_Time": {
        "equipment_min": 30.0,
        "equipment_max": 90.0,
        "lcl": None,
        "target": 60.0,
        "ucl": None,
        "unit": "sec"
    },
    "Press2_Pressure": {
        "equipment_min": 0.0,
        "equipment_max": 20.0,
        "lcl": 9.0,
        "target": 10.0,
        "ucl": 11.0,
        "unit": "kgf/cm²"
    },
    "Press3_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 200.0,
        "lcl": 97.0,
        "target": 100.0,
        "ucl": 103.0,
        "unit": "°C"
    },
    "Press3_Time": {
        "equipment_min": 15.0,
        "equipment_max": 45.0,
        "lcl": None,
        "target": 30.0,
        "ucl": None,
        "unit": "sec"
    },
    "Press3_Pressure": {
        "equipment_min": 0.0,
        "equipment_max": 14.0,
        "lcl": 6.0,
        "target": 7.0,
        "ucl": 8.0,
        "unit": "kgf/cm²"
    },
    "Cure_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 250.0,
        "lcl": 145.0,
        "target": 150.0,
        "ucl": 155.0,
        "unit": "°C"
    },
    "Cure_Time": {
        "equipment_min": 30.0,
        "equipment_max": 90.0,
        "lcl": None,
        "target": 60.0,
        "ucl": None,
        "unit": "min"
    },
    "Anneal_Time": {
        "equipment_min": 0.0,
        "equipment_max": 200.0,
        "lcl": None,
        "target": 90.0,
        "ucl": None,
        "unit": "min"
    },
    "Anneal_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 250.0,
        "lcl": 195.0,
        "target": 200.0,
        "ucl": 205.0,
        "unit": "°C"
    },
    "Peel_Strength": {
        "equipment_min": 0.0,
        "equipment_max": 1000.0,
        "lcl": 350.0,
        "target": 500.0,
        "ucl": None,
        "unit": "kgf/10mm"
    },
    "ABF_Roughness": {
        "equipment_min": 0.0,
        "equipment_max": 1000.0,
        "lcl": 300.0,
        "target": 350.0,
        "ucl": 400.0,
        "unit": "um"
    },
    "Total_Thickness": {
        "equipment_min": 0.0,
        "equipment_max": 37.5,
        "lcl": 30.0,
        "target": 32.0,
        "ucl": 34.0,
        "unit": "um"
    },
    "Yield": {
        "equipment_min": 0.0,
        "equipment_max": 100.0,
        "lcl": 85.0,
        "target": 90.0,
        "ucl": None,
        "unit": "%"
    }
}


PROCESS_PARAMETERS = [
    "CZ_Concentration",
    "Press1_Temp",
    "Press1_Time",
    "Press1_Pressure",
    "Press2_Temp",
    "Press2_Time",
    "Press2_Pressure",
    "Press3_Temp",
    "Press3_Time",
    "Press3_Pressure",
    "Cure_Temp",
    "Cure_Time",
    "Anneal_Time",
    "Anneal_Temp"
]


QUALITY_PARAMETERS = [
    "CZ_Roughness",
    "Peel_Strength",
    "ABF_Roughness",
    "Total_Thickness",
    "Yield",
    "Delamination"
]
