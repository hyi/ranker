import argparse
import json
import time

import httpx


# ---------------------------------------------------------------------------
# ARS configuration — PLACEHOLDERS. Tweak these to point at the desired ARS
# environment (dev / ci / test / prod) and to match the live API shape.
# ---------------------------------------------------------------------------
ARS_BASE_URL = "https://ars-dev.transltr.io"   # placeholder: dev/ci/test/prod
SUBMIT_PATH = "/ars/api/submit"
MESSAGES_PATH = "/ars/api/messages/{pk}"

POLL_INTERVAL = 10      # seconds between parent status polls
MAX_ARS_TIME = 600      # seconds to wait for the parent to reach Done/Error

# Statuses that mean the ARS parent has stopped processing.
TERMINAL_STATUSES = {"Done", "Error"}


def submit_query(payload, base_url=ARS_BASE_URL, client=None):
    """
    Submit a TRAPI query to the ARS and return the parent primary key (pk).

    Returns the pk string on success, or None on HTTP error.
    """
    url = base_url + SUBMIT_PATH
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0))
    try:
        r = client.post(url, json=payload)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"status code: {r.status_code}, HTTP error occurred on submit: {e} "
                  f"with url: {url}")
            return None
        pk = r.json().get("pk")
        if not pk:
            print(f"ARS submit response did not contain a pk: {r.json()}")
            return None
        print(f"ARS submitted, parent pk: {pk}")
        return pk
    finally:
        if owns_client:
            client.close()


def get_merged_message(pk, base_url=ARS_BASE_URL, poll_interval=POLL_INTERVAL,
                       max_time=MAX_ARS_TIME, client=None):
    """
    Poll the ARS parent message until it reaches a terminal status (Done/Error),
    then fetch and return the merged result message.

    Returns the merged TRAPI envelope (a dict with a "message" key) on success,
    or None on timeout / missing merged version / HTTP error.
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0))
    parent_url = base_url + MESSAGES_PATH.format(pk=pk)
    deadline = time.time() + max_time
    try:
        while time.time() < deadline:
            try:
                r = client.get(parent_url, params={"trace": "y"})
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                print(f"HTTP error polling parent {pk}: {e}")
                return None

            data = r.json()
            # The exact JSON paths below (fields.status, fields.merged_version)
            # are the most likely tweak points if the ARS shape differs.
            status = data.get("status")
            # print(f"  ARS parent {pk} status: {status}")

            if status in TERMINAL_STATUSES:
                merged_pk = data.get("merged_version")
                if not merged_pk:
                    print(f"ARS parent {pk} reached '{status}' but has no "
                          f"merged_version")
                    with open("ars_response.json", "w") as f:
                        json.dump(data, f, indent=2)
                    return None
                return _fetch_message(merged_pk, base_url, client)

            time.sleep(poll_interval)

        print(f"ARS parent {pk} timed out after {max_time}s")
        return None
    finally:
        if owns_client:
            client.close()


def _fetch_message(pk, base_url, client):
    """Fetch a single ARS message envelope by pk."""
    url = base_url + MESSAGES_PATH.format(pk=pk)
    try:
        r = client.get(url)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"HTTP error fetching message {pk}: {e}")
        return None
    print(f"  fetched merged message pk: {pk}")
    return r.json()


def run_ars_query(payload, base_url=ARS_BASE_URL):
    """
    Submit a query to the ARS and block until the merged result is available.

    Single entry point for the pipeline (analogous to ranker_scoring.run_query).
    Returns the merged TRAPI envelope, or None on any failure.
    """
    with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
        pk = submit_query(payload, base_url=base_url, client=client)
        if not pk:
            return None
        return get_merged_message(pk, base_url=base_url, client=client)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Submit a TRAPI query to the ARS.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='data/test_queries/trapi_queries.json',
                        help='input file containing a TRAPI query payload')
    parser.add_argument('--output_file', type=str, required=False,
                        default='ars_merged_response.json',
                        help='output file for the ARS merged response')
    parser.add_argument('--ars_url', type=str, required=False,
                        default=ARS_BASE_URL,
                        help='base URL of the ARS environment')

    args = parser.parse_args()

    with open(args.input_file, "r") as f:
        data = json.load(f)

    resp_json = run_ars_query(data, base_url=args.ars_url)

    if resp_json:
        with open(args.output_file, "w") as f:
            json.dump(resp_json, f, indent=2)
        print(f"Merged ARS response saved to {args.output_file}")
    else:
        print(f'no valid merged response returned for the query in {args.input_file}')
    exit(0)
