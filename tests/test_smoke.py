def test_package_importable():
    import tradingwaves

    assert tradingwaves.__version__ == "0.1.0"
