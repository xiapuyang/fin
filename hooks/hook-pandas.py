from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules("pandas._libs") + ["cmath"]

# Exclude tests (~15 MB of .py source files never needed at runtime)
datas = collect_data_files(
    "pandas",
    excludes=["**/tests/**", "**/_testing/**", "**/testing/**"],
)
