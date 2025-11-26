"""CelesTrak API client for fetching TLE data."""

import requests
from typing import Optional, Tuple, Dict, List
from validation import validate_norad_id, validate_tle_format


def search_satellites_by_name(query: str, limit: int = 10) -> List[Dict]:
    """
    Search for satellites by name using CelesTrak's SATCAT database.
    
    Args:
        query: Satellite name or partial name to search for
        limit: Maximum number of results to return
        
    Returns:
        List of dictionaries with keys: norad_id, name, object_type, country, launch_date
    """
    url = "https://celestrak.org/satcat/records.php"
    params = {
        "NAME": query,
        "FORMAT": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        # Check if response is empty
        if not response.text or not response.text.strip():
            return []
        
        try:
            data = response.json()
        except ValueError:
            # Not valid JSON
            return []
        
        # SATCAT returns a list of satellite records
        if isinstance(data, list):
            results = []
            for sat in data[:limit]:
                # Extract NORAD ID and name
                norad_id = sat.get("CATNR") or sat.get("NORAD_CAT_ID")
                name = sat.get("OBJECT_NAME") or sat.get("NAME", "Unknown")
                
                if norad_id:
                    try:
                        results.append({
                            "norad_id": int(norad_id),
                            "name": name,
                            "object_type": sat.get("OBJECT_TYPE", ""),
                            "country": sat.get("COUNTRY", ""),
                            "launch_date": sat.get("LAUNCH_DATE", "")
                        })
                    except (ValueError, TypeError):
                        continue
            
            return results
        return []
        
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
        return int(satellite_identifier)
    except ValueError:
        pass
    
    # Search CelesTrak SATCAT database
    results = search_satellites_by_name(satellite_identifier, limit=1)
    if results:
        # Return the first (best) match
        return results[0]["norad_id"]
    
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
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}"
    
    try:
        # Use allow_redirects=True (equivalent to curl -L) to follow redirects
        response = requests.get(url, allow_redirects=True, timeout=10)
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
        
        lines = response_text.split('\n')
        
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
        raise requests.RequestException(f"Timeout while fetching TLE from CelesTrak for NORAD ID {norad_id}")
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
    
    # Extract satellite name from TLE line 1 (characters 3-23)
    name = line1[2:23].strip() if len(line1) > 23 else "Unknown"
    
    return {
        "norad_id": norad_id,
        "name": name,
        "tle_line1": line1,
        "tle_line2": line2,
    }

