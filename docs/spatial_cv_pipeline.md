# Step 13: 5 km spatial block cross-validation

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System.** This step defines a validation split for the continuous observed LST target. It **does not fit XGBoost or any other model** and reports no accuracy, R², or RMSE.

## Why block validation matters

Nearby 30 m cells often share land cover, weather, source-scene artefacts, and even the same coarser Landsat thermal information. A normal random cell-level `train_test_split` can put neighbours in both training and validation, making the validation result too optimistic for geographically unseen areas. Grouped cross-validation holds out **whole spatial blocks**. The [scikit-learn GroupKFold documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html) describes the same non-overlapping-group principle.

The module implements a deterministic **GroupKFold-equivalent** directly with NumPy. It does not require installing scikit-learn before the modelling step. It balances folds by the number of retained table rows in each block, then exposes a scikit-learn-style `SpatialBlockCV.split()` method for future estimators.

## Exact grid rule

Input `x` and `y` are the Step 12 cell-centre coordinates in **EPSG:32643 metres**. Freeze `x_min = min(x)` and `y_min = min(y)` from the complete training table and use:

`block_x = floor((x − x_min) / 5000)`

`block_y = floor((y − y_min) / 5000)`

`block_id = "block_x:block_y"`

For example, a cell exactly 5,000 m east of `x_min` enters `block_x = 1`; a cell 4,999.9 m east remains in `block_x = 0`. The saved origin and 5,000 m block size must be reused when assigning a later table to the **same** split. Recomputing the minima on a changed dataset can move block boundaries.

Five folds require at least five distinct populated blocks. Sort blocks by descending row count, break ties by numeric block coordinates, and assign each whole block to the currently lightest fold. Fold IDs are 1–5. In fold `k`, all rows of blocks labelled `k` are validation rows; every other block is training. Every retained cell validates exactly once across the five folds. No ward ID, target value, or feature value is used to assign folds.

## Windows PowerShell commands

From the repository root:

```powershell
Set-Location 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-data.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_spatial_cv.py' -v
```

Once Step 12 has produced the **real** `data/processed/greenpulse_ml_grid.parquet` and `data/processed/metadata.json`:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_spatial_cv.py
```

The script reads only `x` and `y` from the ML Parquet, checks its row count and declared CRS/resolution, creates five folds, and confirms for every fold that training and validation block sets are disjoint. It prints the number of held-out blocks and rows per fold. It stops if fewer than five populated blocks exist.

## Outputs after a successful real-data run

- `data/processed/spatial_cv_blocks.parquet`: **one row per populated 5 km block**, with numeric block coordinates, `block_id`, `validation_fold`, and retained-cell count. It does not duplicate the entire ML table.
- `data/processed/spatial_cv_folds.png`: UTM map where every square is coloured by its held-out fold. Empty blocks are left blank. The image is a validation-design map, not a heat map.
- `data/processed/spatial_cv_metadata.json`: source table path, EPSG:32643, block size, frozen x/y minima, exact formula, row count, unique block count, per-fold counts, and the no-overlap QA result.

The real ML Parquet does not yet exist in this workspace, so **no real Pune fold map has been generated**. Unit tests render only an explicitly artificial grid in a temporary directory.

## Verification and scientific limits

For each fold, the module asserts `training block IDs ∩ validation block IDs = ∅`. Tests also verify exact floor boundaries, that every row appears in validation once, deterministic assignments after row reordering, and failure with too few blocks or invalid coordinates.

Whole-block holding reduces the strongest neighbour leakage but does not make adjacent blocks independent. Cells just across a block boundary can share context and source-pixel information; the 3×3 and 5×5 focal features also overlap across borders. Before claiming strict transfer to new areas, compare larger block sizes or add a buffer that removes training cells near held-out blocks. Any future imputation, scaling, feature selection, Optuna tuning, or model fitting must be performed **inside training folds only**, with validation blocks kept untouched.
