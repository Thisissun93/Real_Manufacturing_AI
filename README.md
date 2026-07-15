# Real_Manufacturing_AI
# Manufacturing AI Portfolio

> A Manufacturing AI project that simulates semiconductor package process data and performs process monitoring, statistical analysis, defect analysis, and machine learning based prediction.

---

# Project Overview

This project was built to improve practical Manufacturing AI capabilities.

Instead of using public datasets, this project generates realistic manufacturing process data based on actual semiconductor packaging process relationships and performs statistical analysis, visualization, quality monitoring, and machine learning.

The ultimate goal is to build an intelligent manufacturing analysis platform capable of

- Process Monitoring
- SPC
- Root Cause Analysis
- Defect Prediction
- Explainable AI
- Dashboard Visualization

---

# Project Architecture

```

Raw Process Specification

↓

Synthetic Manufacturing Data Generator

↓

CSV Dataset

↓

Data Loader

↓

EDA

↓

SPC

↓

Correlation Analysis

↓

Defect Analysis

↓

Outlier Detection

↓

Machine Learning

↓

Explainable AI (SHAP)

↓

Dashboard

```

---

# Folder Structure

```text
Real_Manufacturing_AI

│

├── Data
│ └── process_monitoring_data.csv

├── images

├── report

├── src
│
├── data
│ ├── generate_process_data.py
│ └── loader.py
│
├── analysis
│ ├── trend.py
│ ├── spc.py
│ ├── correlation.py
│ ├── defect_analysis.py
│ └── outlier.py
│
├── ml
│ ├── random_forest.py
│ └── shap_analysis.py
│
├── visualization
│
└── process_spec.py

README.md
requirements.txt

```

---

# Dataset

The dataset is automatically generated using manufacturing process specifications.

Current variables include

### Process Parameters

- CZ Concentration
- Press Temperature
- Press Time
- Press Pressure
- Cure Temperature
- Cure Time
- Anneal Temperature
- Anneal Time

### Quality Parameters

- CZ Roughness
- Total Thickness
- Peel Strength
- ABF Roughness

### Output

- Yield
- Defect Type
- Delamination Panel Count

---

# Manufacturing Logic

The generated dataset is not random.

Process relationships are intentionally designed.

Examples

CZ Concentration

↓

CZ Roughness

↓

Peel Strength

↓

ABF Roughness

↓

Delamination Probability

↓

Yield

Additional process relationships

- Higher Press Temperature reduces Total Thickness
- Cure condition influences Peel Strength
- Annealing affects bonding quality
- Yield is calculated from generated defect conditions

---

# Analysis Modules

Current implemented analysis

- Process Trend Analysis
- SPC Control Chart
- Correlation Analysis
- Defect Pareto Analysis
- Outlier Detection
- Automatic Report Generation

---

# Machine Learning

Current model

Random Forest Classifier

Prediction Target

Defect Classification

Outputs

- Prediction Accuracy
- Feature Importance
- Permutation Importance

---

# Explainable AI

SHAP analysis is implemented.

Generated outputs

- SHAP Summary Plot
- SHAP Feature Importance
- SHAP CSV Report

This enables interpretation of why defects are predicted.

---

# Current Project Status

| Module | Status |
|----------|--------|
| Data Generator | ✅ |
| Loader | ✅ |
| Trend Analysis | ✅ |
| SPC | ✅ |
| Correlation | ✅ |
| Defect Analysis | ✅ |
| Outlier Detection | ✅ |
| Random Forest | ✅ |
| SHAP Analysis | ✅ |
| Dashboard | 🚧 |
| PDF Report | 🚧 |

---

# Technology Stack

Python

Pandas

NumPy

Matplotlib

Scikit-learn

SHAP

Git

GitHub

Visual Studio Code

---

# How to Run

Generate dataset

```bash
python -m src.data.generate_process_data
```

Trend Analysis

```bash
python -m src.analysis.trend
```

SPC

```bash
python -m src.analysis.spc
```

Correlation

```bash
python -m src.analysis.correlation
```

Defect Analysis

```bash
python -m src.analysis.defect_analysis
```

Outlier Detection

```bash
python -m src.analysis.outlier
```

Random Forest

```bash
python -m src.ml.random_forest
```

SHAP Analysis

```bash
python -m src.ml.shap_analysis
```

---

# Future Work

- Streamlit Dashboard
- PDF Auto Report
- XGBoost Model
- LightGBM Model
- Anomaly Detection
- DOE Analysis
- Process Optimization
- Predictive Maintenance
- Real-time SPC Monitoring

---

# Author

Manufacturing Engineer

Interested in

- Semiconductor Process
- Process Development
- Statistical Process Control
- Manufacturing AI
- Machine Learning
- Explainable AI

---

# License

MIT License
