"""Oracle HCM Cloud (Fusion) public recruiting adapter — Bug F.

Endpoint pattern:
  GET https://<tenant>.fa.oraclecloud.com/hcmRestApi/resources/latest/
      recruitingCEJobRequisitions?finder=findReqs;siteNumber=<SITE>
      &limit=<N>&onlyData=true&expand=requisitionList

Auth: none (public candidate-experience API).

URL shape in companies.txt: users paste the CNAMEd careers URL
(`https://careers.jpmorgan.com`). `src/url_resolver.py` body-scans the HTML
landing page for the Oracle Fusion HCM URL pattern (`<tenant>.fa.oraclecloud.com
/hcmUI/CandidateExperience/.../sites/<site>/...`) and rewrites
`company.resolved_url`. The adapter then matches on `*.fa.oraclecloud.com`.

Dedup key: `oraclehcm:<tenant>:<requisitionId>`.

Response shape (as of 2026-06-09):
  {
    "items": [
      {
        "TotalJobsCount": 7156,
        "Limit": 25,
        "Offset": 0,
        "requisitionList": [
          {"Id": "210594721", "Title": "...", "PostedDate": "2026-06-08",
           "PrimaryLocation": "Denver, CO, United States", "ShortDescriptionStr": "...",
           "Organization": "...", "JobFamily": "...", ...},
          ...
        ]
      }
    ]
  }

Tested live against jpmorgan (jpmc.fa.oraclecloud.com / siteNumber CX_1001 —
returned 7156 active requisitions).
"""
from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import urlparse

import httpx

from src.adapters.base import Adapter, SchemaDrift, SiteBlocked
from src.models import CompanyConfig, RawPosting

_TIMEOUT_S = 20.0
_PAGE_LIMIT = 25
_COLD_START_CAP_PAGES = 25  # 25 * 25 = 625 postings max on first run

# Parses `<tenant>.fa.oraclecloud.com` from a careers URL.
_TENANT_RE = re.compile(
    r"^https?://(?P<tenant>[a-z0-9-]+)\.fa\.oraclecloud\.com",
    re.IGNORECASE,
)

# Parses `/sites/<SITE>` from a careers URL path. Site numbers are typically
# `CX_1001`, `CX_2`, etc.
_SITE_RE = re.compile(r"/sites/(?P<site>[A-Za-z0-9_-]+)")


class OracleHCMAdapter(Adapter):
    """Adapter for Oracle Fusion HCM Cloud public recruiting JSON API.

    Matches any `*.fa.oraclecloud.com` host. Extracts tenant + site number
    from the resolved URL and calls the public `recruitingCEJobRequisitions`
    endpoint.
    """

    name: ClassVar[str] = "oraclehcm"

    @classmethod
    def matches(cls, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        return host.endswith(".fa.oraclecloud.com")

    @staticmethod
    def _extract_tenant_and_site(url: str) -> tuple[str, str]:
        """Parse `<tenant>.fa.oraclecloud.com/.../sites/<SITE>` into parts.

        Raises SchemaDrift if the URL doesn't match the expected pattern.
        Falls back to `CX_1` for site when the path is just the host (the
        Oracle HCM default).
        """
        m = _TENANT_RE.match(url)
        if m is None:
            raise SchemaDrift(
                f"Oracle HCM URL did not match expected pattern "
                f"(missing <tenant>.fa.oraclecloud.com host): {url}"
            )
        tenant = m.group("tenant")
        sm = _SITE_RE.search(url)
        site = sm.group("site") if sm else "CX_1"
        return tenant, site

    def fetch(self, company: CompanyConfig) -> list[RawPosting]:
        target = company.resolved_url or company.url
        tenant, site = self._extract_tenant_and_site(target)

        collected: list[RawPosting] = []
        for page in range(_COLD_START_CAP_PAGES):
            offset = page * _PAGE_LIMIT
            api_url = (
                f"https://{tenant}.fa.oraclecloud.com/hcmRestApi/resources/"
                f"latest/recruitingCEJobRequisitions"
                f"?finder=findReqs;siteNumber={site}"
                f"&limit={_PAGE_LIMIT}&offset={offset}"
                f"&onlyData=true&expand=requisitionList"
            )
            page_items = self._fetch_page(api_url, company, tenant, site)
            if not page_items:
                break
            collected.extend(page_items)
            if len(page_items) < _PAGE_LIMIT:
                break

        return collected

    def _fetch_page(
        self,
        api_url: str,
        company: CompanyConfig,
        tenant: str,
        site: str,
    ) -> list[RawPosting]:
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "new-grad-tracker/0.1 (+https://github.com/DevDesai444/new-grad)"
            ),
        }
        try:
            response = httpx.get(api_url, headers=headers, timeout=_TIMEOUT_S)
        except httpx.HTTPError:
            raise

        if response.status_code in (403, 429):
            raise SiteBlocked(
                f"OracleHCM {company.name}: HTTP {response.status_code} "
                f"from {api_url}"
            )
        if response.status_code >= 500:
            raise SiteBlocked(
                f"OracleHCM {company.name}: HTTP {response.status_code} "
                f"(server error) from {api_url}"
            )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as e:
            raise SchemaDrift(
                f"OracleHCM {company.name}: response body is not JSON"
            ) from e

        if not isinstance(payload, dict) or "items" not in payload:
            got = (
                list(payload.keys())
                if isinstance(payload, dict)
                else type(payload).__name__
            )
            raise SchemaDrift(
                f"OracleHCM {company.name}: missing top-level 'items' "
                f"(got: {got})"
            )
        outer_items = payload["items"]
        if not isinstance(outer_items, list) or not outer_items:
            return []
        outer = outer_items[0]
        if not isinstance(outer, dict):
            raise SchemaDrift(
                f"OracleHCM {company.name}: items[0] is not a dict"
            )
        reqs = outer.get("requisitionList")
        if reqs is None:
            # No more results — empty page.
            return []
        if not isinstance(reqs, list):
            raise SchemaDrift(
                f"OracleHCM {company.name}: 'requisitionList' is not a list "
                f"(got {type(reqs).__name__})"
            )

        result: list[RawPosting] = []
        for req in reqs:
            if not isinstance(req, dict) or "Id" not in req:
                continue
            req_id = str(req["Id"])
            enriched = dict(req)
            enriched["__dedup_key"] = f"oraclehcm:{tenant}:{req_id}"
            enriched["__tenant"] = tenant
            enriched["__site"] = site
            enriched["__posting_url"] = (
                f"https://{tenant}.fa.oraclecloud.com/hcmUI/CandidateExperience/"
                f"en/sites/{site}/job/{req_id}"
            )
            result.append(
                RawPosting(
                    source_company=company.name,
                    source_adapter=self.name,
                    raw=enriched,
                )
            )

        return result


__all__ = ["OracleHCMAdapter"]
