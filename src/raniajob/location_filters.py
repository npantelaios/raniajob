from __future__ import annotations

import re
from typing import List, Set, Optional


def extract_us_state_from_location(location: str) -> Optional[str]:
    """
    Extract US state abbreviation from location string.
    Handles various formats like:
    - "Boston, MA"
    - "New York, NY, USA"
    - "Philadelphia, PA, United States"
    - "Remote - New Jersey"
    - "Princeton, NJ (Remote)"
    """
    if not location:
        return None

    # Common US state abbreviations
    us_states = {
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
        'DC'  # Washington DC
    }

    # State name to abbreviation mapping for full state names
    state_name_to_abbrev = {
        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
        'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
        'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
        'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
        'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
        'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
        'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
        'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
        'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
        'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
        'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
        'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
        'wisconsin': 'WI', 'wyoming': 'WY', 'district of columbia': 'DC'
    }

    location_clean = location.strip().upper()

    # Pattern 1: Look for state abbreviations (2 letters)
    # Match patterns like "Boston, MA" or "New York, NY, USA"
    state_abbrev_pattern = r'[,\s]\s*([A-Z]{2})(?:[,\s]|$)'
    match = re.search(state_abbrev_pattern, location_clean)
    if match:
        potential_state = match.group(1)
        if potential_state in us_states:
            return potential_state

    # Pattern 2: Look for full state names
    location_lower = location.lower()
    for state_name, abbrev in state_name_to_abbrev.items():
        if state_name in location_lower:
            # Make sure it's a word boundary match to avoid partial matches
            pattern = r'\b' + re.escape(state_name) + r'\b'
            if re.search(pattern, location_lower):
                return abbrev

    # Pattern 3: Special cases for major cities that clearly indicate states
    city_to_state = {
        'boston': 'MA', 'cambridge': 'MA', 'worcester': 'MA', 'springfield': 'MA',
        'new york': 'NY', 'nyc': 'NY', 'brooklyn': 'NY', 'manhattan': 'NY', 'albany': 'NY',
        'philadelphia': 'PA', 'pittsburgh': 'PA', 'harrisburg': 'PA',
        'newark': 'NJ', 'jersey city': 'NJ', 'trenton': 'NJ', 'princeton': 'NJ'
    }

    for city, state in city_to_state.items():
        if city in location_lower:
            return state

    return None


def is_location_in_target_states(location: str, target_states: Set[str]) -> bool:
    """
    Check if a location string indicates a job in one of the target US states.

    Args:
        location: Location string from job posting
        target_states: Set of state abbreviations (e.g., {'NY', 'NJ', 'PA', 'MA'})

    Returns:
        True if location is in target states, False otherwise
    """
    state = extract_us_state_from_location(location)
    return state in target_states if state else False


def filter_jobs_by_location(jobs: List, target_states: Set[str]) -> List:
    """
    Filter a list of JobPosting objects to only include jobs in target US states.

    Args:
        jobs: List of JobPosting objects
        target_states: Set of state abbreviations (e.g., {'NY', 'NJ', 'PA', 'MA'})

    Returns:
        Filtered list of jobs in target states
    """
    filtered_jobs = []

    for job in jobs:
        # Check if job has location information
        location_sources = []

        # For JobSpy jobs, check if the job object has location attribute
        if hasattr(job, 'location') and job.location:
            location_sources.append(job.location)

        # Check description for location info
        if hasattr(job, 'description') and job.description:
            # Look for location patterns in description
            location_patterns = [
                r'Location[:\s]+([^,\n]+(?:,[^,\n]+)*)',
                r'Based in[:\s]+([^,\n]+(?:,[^,\n]+)*)',
                r'Office[:\s]+([^,\n]+(?:,[^,\n]+)*)',
            ]

            for pattern in location_patterns:
                matches = re.findall(pattern, job.description, re.IGNORECASE)
                location_sources.extend(matches)

        # If no specific location found, check if it's remote
        # Remote jobs are acceptable if they specify US states
        if not location_sources:
            if hasattr(job, 'description') and job.description:
                if any(term in job.description.lower() for term in ['remote', 'work from home', 'telecommute']):
                    # For remote jobs, be more permissive but still check if US states are mentioned
                    us_mentions = re.findall(r'\b(US|USA|United States)\b', job.description, re.IGNORECASE)
                    if us_mentions:
                        filtered_jobs.append(job)
                        continue

        # Check each location source
        job_in_target_area = False
        for location in location_sources:
            if is_location_in_target_states(location, target_states):
                job_in_target_area = True
                break

        if job_in_target_area:
            filtered_jobs.append(job)

    return filtered_jobs


def get_default_target_states() -> Set[str]:
    """Get the default target states: NY, NJ, PA, MA"""
    return {'NY', 'NJ', 'PA', 'MA'}


def get_target_state_locations() -> List[str]:
    """Get major cities/areas in target states for JobSpy searches"""
    return [
        "New York, NY",
        "Boston, MA",
        "Philadelphia, PA",
        "Newark, NJ",
        "Cambridge, MA",
        "Pittsburgh, PA",
        "Jersey City, NJ",
        "Albany, NY"
    ]
