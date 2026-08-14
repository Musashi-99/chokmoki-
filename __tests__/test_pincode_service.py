from src.services.pincode_service import is_valid_pincode, parse_india_post


def test_is_valid_pincode():
    assert is_valid_pincode("700016") is True
    assert is_valid_pincode("110001") is True
    assert is_valid_pincode("70001") is False
    assert is_valid_pincode("7000161") is False
    assert is_valid_pincode("70a016") is False
    assert is_valid_pincode("") is False


def test_parse_india_post_success():
    payload = [
        {
            "Status": "Success",
            "PostOffice": [
                {
                    "Name": "Park Street",
                    "DeliveryStatus": "Delivery",
                    "District": "Kolkata",
                    "State": "West Bengal",
                    "Country": "India",
                }
            ],
        }
    ]
    assert parse_india_post(payload) == {
        "city": "Kolkata",
        "state": "West Bengal",
        "country": "India",
        "locality": "Park Street",
    }


def test_parse_india_post_prefers_delivery_office():
    payload = [
        {
            "Status": "Success",
            "PostOffice": [
                {
                    "Name": "Sorting",
                    "DeliveryStatus": "Non-Delivery",
                    "District": "Mumbai",
                    "State": "Maharashtra",
                    "Country": "India",
                },
                {
                    "Name": "Fort",
                    "DeliveryStatus": "Delivery",
                    "District": "Mumbai",
                    "State": "Maharashtra",
                    "Country": "India",
                },
            ],
        }
    ]
    assert parse_india_post(payload)["locality"] == "Fort"


def test_parse_india_post_invalid():
    assert parse_india_post(None) is None
    assert parse_india_post([]) is None
    assert parse_india_post([{"Status": "Error", "PostOffice": None}]) is None
    assert parse_india_post([{"Status": "Success", "PostOffice": []}]) is None
