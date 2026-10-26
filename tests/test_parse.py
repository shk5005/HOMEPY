from pathlib import Path

import pytest

from homepy.parse import ApiError, parse_page

FIXTURES = Path(__file__).parent / "fixtures"
OK = ("000",)


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_two_items():
    p = parse_page(read("page_two_items.xml"), OK)
    assert p.total_count == 2 and len(p.items) == 2
    assert p.items[0]["dealAmount"] == "82,500"
    assert p.items[0]["cdealType"] == ""


def test_empty_month_is_zero_not_error():
    p = parse_page(read("page_empty.xml"), OK)
    assert p.total_count == 0 and p.items == ()


def test_single_item():
    assert len(parse_page(read("page_one_item.xml"), OK).items) == 1


@pytest.mark.parametrize("name", ["error_result_code.xml", "error_service_response.xml"])
def test_api_errors_raise(name):
    with pytest.raises(ApiError):
        parse_page(read(name), OK)


def test_malformed_xml_raises_api_error():
    with pytest.raises(ApiError):
        parse_page(b"<html>gateway timeout", OK)
