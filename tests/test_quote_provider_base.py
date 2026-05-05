"""Tests for QuoteProvider ABC contract."""

import pytest

from fin.services.providers.base import QuoteProvider


class _FullProvider(QuoteProvider):
    def supports(self, symbol):
        return True

    def fetch_live(self, symbol):
        return {"price": 1.0}

    def fetch_full(self, symbol):
        return {"price": 1.0, "name": "Test"}


class _MissingFetchFull(QuoteProvider):
    def supports(self, symbol):
        return True

    def fetch_live(self, symbol):
        return {}


def test_full_implementation_is_instantiable():
    p = _FullProvider()
    assert p.supports("AAPL") is True
    assert p.fetch_live("AAPL")["price"] == 1.0
    assert p.fetch_full("AAPL")["name"] == "Test"


def test_missing_abstract_method_raises_type_error():
    with pytest.raises(TypeError):
        _MissingFetchFull()


def test_fetch_fx_default_raises_not_implemented():
    p = _FullProvider()
    with pytest.raises(NotImplementedError):
        p.fetch_fx({"USD": "USDCNY=X"})
