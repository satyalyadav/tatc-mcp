from tatc_mcp import celestrak_client


def test_fetch_tle_requests_tle_format_and_parses_three_lines(monkeypatch):
    line1 = "1 " + ("0" * 67)
    line2 = "2 " + ("0" * 67)

    class FakeResponse:
        text = f"ISS (ZARYA)\n{line1}\n{line2}\n"

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        assert url == celestrak_client.GP_TLE_URL
        assert kwargs["params"] == {"CATNR": 25544, "FORMAT": "TLE"}
        assert kwargs["allow_redirects"] is True
        assert kwargs["timeout"] == 10
        return FakeResponse()

    monkeypatch.setattr(celestrak_client.requests, "get", fake_get)

    assert celestrak_client.fetch_tle(25544) == (line1, line2)
