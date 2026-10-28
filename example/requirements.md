# Requirements

Priority: **M**ust and **S**hould need a passing test (`prove-it trace` enforces it); **C**ould
doesn't. Every test cites the IDs it covers with `@pytest.mark.req(...)`.

| ID | Requirement | Pri |
|---|---|---|
| REQ-SPL-01 | Shares always sum to exactly the bill total, to the cent | M |
| REQ-SPL-02 | Each share is within one cent of its exact proportional amount | M |
| REQ-SPL-03 | Leftover cents go to the largest fractional remainders; ties go to the earliest payer | M |
| REQ-SPL-04 | Amounts parse from text such as "12.34" without floating point | S |
| REQ-SPL-05 | A tip can be added as a percentage of the bill | C |
| REQ-SPL-06 | *Retired*: an even split only (replaced by weighted shares, REQ-SPL-02) | M |
| REQ-NFR-01 | Money code never uses float | M |
