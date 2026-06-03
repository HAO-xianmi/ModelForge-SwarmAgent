# Short-Term Electricity Demand Forecasting (prediction / time series)

**Category:** prediction / forecasting (time series)

A utility provides three years of hourly electricity demand for a metropolitan
area, together with weather (temperature, humidity, wind), calendar features
(hour, weekday, holiday), and a coarse economic activity index.

**Q1.** Build a model to forecast hourly demand 24–168 hours ahead. Engineer
features that capture daily/weekly seasonality and weather dependence; justify the
model family.

**Q2.** Quantify forecast accuracy out-of-sample (RMSE, MAE, MAPE) and compare
against at least one baseline (e.g. seasonal-naive or linear). The proposed model
must beat the baseline visibly, and the test-vs-cross-validation gap must be
reported honestly.

**Q3.** Characterize uncertainty: produce prediction intervals and analyze when
the model fails (heat waves, holidays, regime shifts).

**Q4.** Sensitivity: how does accuracy change with training-window length, feature
subsets, and forecast horizon? Identify the most important features.

**Deliverable.** A competition paper with assumptions, a symbol table, the
forecasting model and feature engineering with formulas, baseline-beating
validation with metrics and figures, an error/uncertainty and feature-importance
sensitivity analysis, result tables, and a strengths/weaknesses discussion.
