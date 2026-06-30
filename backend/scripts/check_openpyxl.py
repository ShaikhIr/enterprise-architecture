try:
    import openpyxl
    print("openpyxl available:", openpyxl.__version__)
except ImportError:
    print("openpyxl NOT installed")
