[1mdiff --cc export_processed.py[m
[1mindex 87e6da4,7d4602b..0000000[m
[1m--- a/export_processed.py[m
[1m+++ b/export_processed.py[m
[36m@@@ -31,7 -31,8 +31,15 @@@[m [mout_dir.mkdir(parents=True, exist_ok=Tr[m
  [m
  full_ml_matrix.to_csv(out_dir / "full_ml_feature_matrix.csv", index=False)[m
  stores.to_csv(out_dir / "stores_metadata.csv", index=False)[m
[32m++<<<<<<< HEAD[m
[32m +items.to_csv(out_dir / "items_catalog.csv", index=False)  # Added alias export[m
[32m +cold_start_priors.to_csv(out_dir / "cold_start_priors.csv", index=False)[m
[32m +[m
[31m- print("Export complete! Files saved to data/processed/")[m
[32m++print("Export complete! Files saved to data/processed/")[m
[32m++=======[m
[32m+ items.to_csv(out_dir / "items_catalog.csv", index=False)[m
[32m+ items.to_csv(out_dir / "products_catalog.csv", index=False)  # Added alias export[m
[32m+ cold_start_priors.to_csv(out_dir / "cold_start_priors.csv", index=False)[m
[32m+ [m
[32m+ print("Export complete! Files saved to data/processed/")[m
[32m++>>>>>>> 44cf686fce55339a950cf698390fdc39b7eb4bdb[m
