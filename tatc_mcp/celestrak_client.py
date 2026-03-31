"""CelesTrak API client for fetching TLE data."""

import re
from typing import Any, Dict, List, Optional, Tuple

import requests

from tatc_mcp.validation import validate_norad_id, validate_tle_format


SATCAT_URL = "https://celestrak.org/satcat/records.php"
GP_TLE_URL = "https://celestrak.org/NORAD/elements/gp.php"
GP_JSON_URL = "https://celestrak.org/NORAD/elements/gp.php"

# A few common colloquial names need explicit mapping because CelesTrak NAME search
# is substring-based and can otherwise resolve to unrelated historical objects.
_COMMON_NAME_ALIASES = {
    "ISS": 25544,
    "INTERNATIONAL SPACE STATION": 25544,
    "INTERNATIONAL SPACE STATION ISS": 25544,
    "ISS ZARYA": 25544,
    "HUBBLE": 20580,
    "HUBBLE SPACE TELESCOPE": 20580,
    "HST": 20580,
    "JAMES WEBB": 50463,
    "JAMES WEBB SPACE TELESCOPE": 50463,
    "JWST": 50463,
}


def _normalize_name(value: str) -> str:
    """Normalize a name for case-insensitive matching."""
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", value.upper()).split())


def _parse_json_response(response: requests.Response) -> Any:
    """Parse a JSON response that may be empty."""
    if not response.text or not response.text.strip():
        return []
    return response.json()


def _format_satcat_record(sat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a SATCAT record to the public search schema."""
    norad_id = sat.get("CATNR") or sat.get("NORAD_CAT_ID")
    name = sat.get("OBJECT_NAME") or sat.get("NAME", "Unknown")

    if not norad_id:
        return None

    try:
        return {
            "norad_id": int(norad_id),
            "name": name,
            "object_type": sat.get("OBJECT_TYPE", ""),
            "country": sat.get("COUNTRY") or sat.get("OWNER", ""),
            "launch_date": sat.get("LAUNCH_DATE", ""),
        }
    except (ValueError, TypeError):
        return None


def _fetch_satcat_records(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch raw SATCAT records for a search query."""
    response = requests.get(
        SATCAT_URL,
        params={"NAME": query, "FORMAT": "json"},
        timeout=15,
    )
    response.raise_for_status()

    data = _parse_json_response(response)
    if not isinstance(data, list):
        return []

    records: List[Dict[str, Any]] = []
    for sat in data[:limit]:
        formatted = _format_satcat_record(sat)
        if formatted is not None:
            records.append(formatted)
    return records


def _score_search_result(query: str, candidate_name: str) -> int:
    """Score a search candidate for deterministic ranking."""
    normalized_query = _normalize_name(query)
    normalized_candidate = _normalize_name(candidate_name)
    if not normalized_query or not normalized_candidate:
        return 0

    query_tokens = normalized_query.split()
    candidate_tokens = normalized_candidate.split()
    score = 0

    if normalized_candidate == normalized_query:
        score += 100
    if normalized_candidate.startswith(normalized_query):
        score += 40
    if normalized_query in normalized_candidate:
        score += 20
    if all(token in candidate_tokens for token in query_tokens):
        score += 15
    if any(token == normalized_query for token in candidate_tokens):
        score += 10

    # Prefer tighter matches when the score would otherwise tie.
    score -= abs(len(candidate_tokens) - len(query_tokens))
    return score


def _rank_search_results(query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return search results in descending relevance order."""
    return sorted(
        results,
        key=lambda item: (_score_search_result(query, item["name"]), -item["norad_id"]),
        reverse=True,
    )


def _fetch_gp_metadata(norad_id: int) -> Optional[Dict[str, Any]]:
    """Fetch current GP metadata for a NORAD ID."""
    response = requests.get(
        GP_JSON_URL,
        params={"CATNR": validate_norad_id(norad_id), "FORMAT": "json"},
        timeout=15,
    )
    response.raise_for_status()

    data = _parse_json_response(response)
    if isinstance(data, list) and data:
        item = data[0]
        return {
            "norad_id": int(item.get("NORAD_CAT_ID", norad_id)),
            "name": item.get("OBJECT_NAME", "").strip(),
            "object_id": item.get("OBJECT_ID", "").strip(),
        }
    return None


def _resolve_alias(identifier: str) -> Optional[int]:
    """Resolve a curated common-name alias to a NORAD ID."""
    return _COMMON_NAME_ALIASES.get(_normalize_name(identifier))


def _resolve_search_result(identifier: str) -> Optional[Dict[str, Any]]:
    """Resolve a text identifier to a single search result or raise if ambiguous."""
    results = search_satellites_by_name(identifier, limit=10)
    if not results:
        return None

    top_score = _score_search_result(identifier, results[0]["name"])
    if top_score < 40:
        raise ValueError(
            f"Satellite identifier '{identifier}' is ambiguous. "
            f"Use search_satellites first, then provide an exact name or NORAD ID."
        )

    if len(results) > 1:
        second_score = _score_search_result(identifier, results[1]["name"])
        if second_score == top_score:
            raise ValueError(
                f"Satellite identifier '{identifier}' matches multiple satellites. "
                f"Use search_satellites first, then provide an exact name or NORAD ID."
            )

    return results[0]


def search_satellites_by_name(query: str, limit: int = 10) -> List[Dict]:
    """
    Search for satellites by name using CelesTrak's SATCAT database.

    Args:
        query: Satellite name or partial name to search for
        limit: Maximum number of results to return

    Returns:
        List of dictionaries with keys: norad_id, name, object_type, country, launch_date
    """
    try:
        results = _fetch_satcat_records(query, limit=max(limit, 25))
        ranked_results = _rank_search_results(query, results)
        return ranked_results[:limit]

    except requests.RequestException:
        # Silently return empty list for network errors
        return []
    except Exception:
        # Silently return empty list for parsing errors
        return []


def get_norad_id(satellite_identifier: str) -> Optional[int]:
    """
    Convert satellite name or NORAD ID string to integer NORAD ID.
    Uses CelesTrak SATCAT database for name lookups.

    Args:
        satellite_identifier: Satellite name (case-insensitive) or NORAD ID as string

    Returns:
        NORAD ID as integer, or None if not found
    """
    # Try to parse as integer first
    try:
        return validate_norad_id(int(satellite_identifier))
    except ValueError:
        pass

    alias_norad_id = _resolve_alias(satellite_identifier)
    if alias_norad_id is not None:
        return alias_norad_id

    resolved = _resolve_search_result(satellite_identifier)
    if resolved:
        return resolved["norad_id"]

    return None


def fetch_tle(norad_id: int) -> Tuple[str, str]:
    """
    Fetch TLE data from CelesTrak for a given NORAD ID.

    Args:
        norad_id: NORAD catalog number

    Returns:
        Tuple of (line1, line2) TLE strings

    Raises:
        ValueError: If TLE data cannot be fetched or parsed
        requests.RequestException: If API request fails
    """
    # Validate NORAD ID
    norad_id = validate_norad_id(norad_id)

    # Don't use FORMAT=tle parameter - it causes 403 errors
    # The default format is TLE, so we don't need to specify it
    try:
        response = requests.get(
            GP_TLE_URL,
            params={"CATNR": norad_id},
            allow_redirects=True,
            timeout=10,
        )
        response.raise_for_status()

        # Check if response is empty or indicates no data
        response_text = response.text.strip()
        if not response_text:
            raise ValueError(f"No TLE data returned from CelesTrak for NORAD ID {norad_id}")

        # Check for common error messages from CelesTrak
        if "No GP data found" in response_text or "not found" in response_text.lower():
            raise ValueError(
                f"TLE data not available for NORAD ID {norad_id}. "
                f"The satellite may have decayed, been decommissioned, or the ID may be incorrect. "
                f"Response: {response_text[:200]}"
            )

        lines = response_text.split("\n")

        # Filter out empty lines
        lines = [line.strip() for line in lines if line.strip()]

        if len(lines) < 2:
            raise ValueError(
                f"Invalid TLE format: expected at least 2 lines, got {len(lines)}. "
                f"Response: {response_text[:200]}"
            )

        # TLE format: first line is satellite name, second and third are TLE lines
        # Sometimes the name line is included, sometimes not
        if len(lines) >= 3:
            # Has name line, TLE lines are 2nd and 3rd
            line1 = lines[1]
            line2 = lines[2]
        else:
            # Just TLE lines
            line1 = lines[0]
            line2 = lines[1]

        # Validate TLE format
        line1, line2 = validate_tle_format(line1, line2)

        return line1, line2

    except requests.Timeout:
        raise requests.RequestException(
            f"Timeout while fetching TLE from CelesTrak for NORAD ID {norad_id}"
        )
    except requests.HTTPError as e:
        raise requests.RequestException(
            f"HTTP error {e.response.status_code} while fetching TLE from CelesTrak: {e}"
        )
    except requests.RequestException as e:
        raise requests.RequestException(f"Failed to fetch TLE from CelesTrak: {e}")
    except ValueError:
        # Re-raise validation errors
        raise
    except Exception as e:
        raise ValueError(f"Unexpected error parsing TLE data: {e}")


def fetch_tle_by_name(satellite_name: str) -> Tuple[str, str]:
    """
    Fetch TLE data by satellite name.

    Args:
        satellite_name: Satellite name (will be searched in CelesTrak database)

    Returns:
        Tuple of (line1, line2) TLE strings

    Raises:
        ValueError: If satellite name cannot be resolved to NORAD ID or TLE fetch fails
    """
    norad_id = get_norad_id(satellite_name)
    if norad_id is None:
        raise ValueError(
            f"Satellite '{satellite_name}' not found. "
            f"Please provide a valid satellite name or NORAD ID."
        )
    return fetch_tle(norad_id)


def get_satellite_info(satellite_identifier: str) -> Dict:
    """
    Get satellite information including TLE data.

    Args:
        satellite_identifier: Satellite name or NORAD ID

    Returns:
        Dictionary with satellite information:
        - norad_id: NORAD catalog number
        - name: Satellite name (if available)
        - tle_line1: First TLE line
        - tle_line2: Second TLE line
    """
    norad_id = get_norad_id(satellite_identifier)
    if norad_id is None:
        raise ValueError(
            f"Could not resolve satellite identifier '{satellite_identifier}' to NORAD ID"
        )

    line1, line2 = fetch_tle(norad_id)
    metadata = _fetch_gp_metadata(norad_id)

    if metadata and metadata.get("name"):
        name = metadata["name"]
    else:
        # Fall back to the ranked search result name if GP metadata is unavailable.
        resolved = None
        if not str(satellite_identifier).strip().isdigit():
            try:
                resolved = _resolve_search_result(satellite_identifier)
            except ValueError:
                resolved = None
        name = resolved["name"] if resolved else f"NORAD {norad_id}"

    return {
        "norad_id": norad_id,
        "name": name,
        "tle_line1": line1,
        "tle_line2": line2,
    }
