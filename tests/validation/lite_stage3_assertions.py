"""Hand-authored phase-three source expectations, before fresh compilation.

Only the selected expected text is evidence. Parent line chains are explicit
independent assertions; their literal wording is resolved from that input,
never from a generated graph. All legal clauses use the approved complete
content contract, including their conditions, exceptions and references.
"""

SAMPLE = 'tencent-covenants-interest-conditions-p118-123'

REVIEW_ASSERTIONS = {
    SAMPLE: ('complex-tencent-2025-bond-programme', [118, 119, 120, 121, 122, 123],
        [(1640, 1657), (1658, 1665), (1666, 1666), (1667, 1675),
         (1676, 1688), (1689, 1701), (1702, 1717)], '''
1640|H2|5. Certain Covenants
1642|H3|(a) Negative Pledge
1644|P|So long as any Note remains outstanding~Issuer will not create~none of its Material Controlled Entities~present or future~without (a)~equally and rateably~or (b)~Extraordinary Resolution
1646|H3|(b) Consolidation, Merger and Sale of Assets
1648|P|Issuer will not consolidate~not the surviving entity~substantially as an entirety~unless:
1650|I|(i) any Person formed~Cayman Islands or Hong Kong~expressly assumes~all the obligations~Additional Amounts~Condition 13 (Taxation)~subject to exclusions equivalent
1651|I|(ii) immediately after~no Event of Default~notice or lapse of time or both~shall have occurred; and
1652|I|(iii) the Issuer has delivered~Officers’ Certificate and an Opinion of Counsel~each stating~all conditions precedent~have been complied with
1654|H3|(c) Reports
1656|I|(i) So long as any Notes remain outstanding~Trustee~Noteholders upon request~not more than 30 calendar days~SEHK~provided that if~ceases to be listed~holders upon request:
1657|I|(A) as soon as~within 120 calendar days~end of the fiscal year~consolidated basis~year-to-year comparison~audited~independent accountants
1658|I|(B) as soon as~within 90 calendar days~first semi-annual fiscal period~unaudited~period-to-period comparison~reviewed~certificate signed~true in all material respects~present fairly
1659|I|(C) as soon as~within 60 calendar days~first and third fiscal quarters~unaudited~period-to-period comparison~certificate signed~present fairly~and
1660|I|(D) as soon as possible~within 14 calendar days~Issuer becomes aware~notice or lapse of time or both~Event of Default~Officers’ Certificate~taking or proposes to take
1661|I|(ii) So long as~Restricted Notes~Rule 144(a)(3)~upon the request~paragraph (d)(4) of Rule 144A~qualified institutional buyer~to the extent required~unless~Section 13 or 15(d)~Rule 12g3-2(b)
1663|H2|6. Fixed Rate Note Provisions
1665|I|(a) Application:~only if~Fixed Rate Note Provisions~relevant Pricing Supplement
1666|I|(b) Accrual of interest:~Interest Commencement Date~payable in arrears~Conditions 11~12~cease to bear interest~unless~withheld or refused~whichever is the earlier~seven days~except to the extent~subsequent default
1667|I|(c) Fixed Coupon Amount:~each Note~any Interest Period~more than one Specified Denomination~relevant Fixed Coupon Amount
1668|I|(d) Calculation of interest amount:~not specified~Rate of Interest~Calculation Amount~Day Count Fraction~nearest sub-unit~half a sub-unit being rounded upwards~Specified Denomination~other than euro~legal tender~euro, means one cent
1670|H2|7. Floating Rate Note and Index-Linked Interest Note Provisions
1672|I|(a) Application:~only if~Floating Rate Note Provisions or the Index-Linked Interest Note Provisions
1673|I|(b) Accrual of interest:~Interest Commencement Date~payable in arrears~Conditions 11~12~unless~withheld or refused~whichever is the earlier~seven days~except to the extent~subsequent default
1674|I|(c) Screen Rate Determination~other than~SOFR~If Screen Rate Determination~other than in respect~Calculation Agent~following basis:
1675|I|(i) if the Reference Rate~composite quotation or customarily supplied by one entity~Calculation Agent~Relevant Screen Page~Relevant Time~Interest Determination Date
1676|I|(ii) if Linear Interpolation~Interest Period~Calculation Agent~straight-line linear interpolation~two rates~where:
1677|I|(A) one rate~next shorter~length of the relevant Interest Period~and
1678|I|(B) the other rate~next longer~length of the relevant Interest Period
1680|I|provided, however~if no rate is available~next shorter~next longer~Issuer shall appoint an Independent Adviser~Condition 7(h)(viii)~instructions from the Issuer~sources as it determines appropriate
1682|I|(iii) in any other case~Calculation Agent~arithmetic mean~Relevant Screen Page~Relevant Time~Interest Determination Date
1683|I|(iv) if~(i) above~does not appear~(iii) above~fewer than two~unavailable~sum of the Margin~arithmetic mean last determined~preceding Interest Period
1684|I|(d) ISDA Determination:~If ISDA Determination~sum of the Margin~ISDA Rate~Floating Rate~Calculation Agent~interest rate swap transaction~under which:
1685|I|(i) if the Pricing Supplement~2006 ISDA Definitions~or~2021 ISDA Definitions~applicable ISDA Definitions:
1686|I|(A) the Floating Rate Option~specified in the relevant Pricing Supplement
1687|I|(B) the Designated Maturity~if applicable~period specified~Pricing Supplement
1688|I|(C) the relevant Reset Date~unless otherwise specified~meaning given~ISDA Definitions
1689|I|(D) if Linear Interpolation~Calculation Agent~straight-line linear interpolation~two rates~relevant Floating Rate Option~where:
1690|I|(1) one rate~Designated Maturity~next shorter~and
1691|I|(2) the other rate~Designated Maturity~next longer
1693|I|provided, however~if no rate is available~Issuer shall appoint~Independent Adviser~instructions from the Issuer~sources as it determines appropriate
1695|I|(E) if the specified Floating Rate Option~Overnight Floating Rate Option~Compounding~applicable~and:
1696|I|(1) if Compounding with Lookback~then (a)~Overnight Rate Compounding Method~(b) Lookback~Applicable Business Days~Pricing Supplement
1697|I|(2) if Compounding with Observation Period Shift~then (a)~(b)~Observation Period Shift Business Days~(c)~Additional Business Days~if applicable~or
1698|I|(3) if Compounding with Lockout~then (a)~(b)~Lockout Period Business Days~(c)~if applicable
1699|I|(F) if the specified Floating Rate Option~Overnight Floating Rate Option~Averaging~applicable~and:
1700|I|(1) if Averaging with Lookback~then (a)~Overnight Rate Averaging Method~(b) Lookback~Applicable Business Days
1701|I|(2) if Averaging with Observation Period Shift~then (a)~(b)~Observation Period Shift Business Days~(c)~Additional Business Days~if applicable~or
1702|I|(3) if Averaging with Lockout~then (a)~(b)~Lockout Period Business Days~(c)~if applicable~and
1703|I|(G) if the specified Floating Rate Option~Index Floating Rate Option~and Index Provisions~Compounded Index Method with Observation Period Shift~(a)~(b)~Additional Business Days~if applicable
1704|I|(ii) references in the ISDA Definitions to:
1705|I|(A) “Confirmation”~references to the relevant Pricing Supplement
1706|I|(B) “Calculation Period”~references to the relevant Interest Period
1707|I|(C) “Termination Date”~references to the Maturity Date~and
1708|I|(D) “Effective Date”~references to the Interest Commencement Date~and
1709|I|(iii) if the Pricing Supplement~2021 ISDA Definitions~applicable:
1710|I|(A) “Administrator/Benchmark Event”~shall be disapplied~and
1711|I|(B) if the Temporary Non-Publication Fallback~Temporary Non-Publication Fallback — Alternative Rate~Floating Rate Matrix~2021 ISDA Definitions~Calculation Agent Alternative Rate Determination~shall be replaced~Temporary Non-Publication Fallback — Previous Day’s Rate
1712|I|(e) Index-Linked Interest:~If~applicable~each Interest Period~manner specified~Pricing Supplement
1714|H3|(f) Interest — Floating Rate Notes referencing SOFR (Screen Rate Determination)
1716|I|(i) This Condition 7(f)~only if~Floating Rate Note Provisions~Screen Rate Determination~and~Reference Rate~Compounded SOFR~or~SOFR Compounded Index
1717|I|(ii) Where~Compounded SOFR~Benchmark plus or minus~as specified~Margin~Calculation Agent~each Interest Determination Date
''')}

# Independent physical ancestry, including three nested levels. Sibling
# condition groups must never borrow one another's actor, period or exception.
PARENTS = {
    **{n: [1656] for n in (1657, 1658, 1659, 1660)},
    **{n: [1674] for n in (1675, 1676, 1682, 1683)},
    1680: [1674, 1676],
    **{n: [1674, 1676] for n in (1677, 1678)},
    **{n: [1684] for n in (1685, 1704, 1709)},
    **{n: [1684, 1685] for n in (1686, 1687, 1688, 1689, 1695, 1699, 1703)},
    1693: [1684, 1685, 1689],
    **{n: [1684, 1685, 1689] for n in (1690, 1691)},
    **{n: [1684, 1685, 1695] for n in (1696, 1697, 1698)},
    **{n: [1684, 1685, 1699] for n in (1700, 1701, 1702)},
    **{n: [1684, 1704] for n in (1705, 1706, 1707, 1708)},
    **{n: [1684, 1709] for n in (1710, 1711)},
}
REVIEW_SOURCE_OVERRIDES = {(SAMPLE, line): {'parent_lines': parents} for line, parents in PARENTS.items()}
REVIEW_ORDERED_SOURCE_GROUPS = {SAMPLE: [
    (1656, 1661, 'Reporting trigger, four nested deadlines and separate restricted-note exception retain their printed order and parent chains.'),
    (1672, 1712, 'Floating-rate conditions, nested alternatives, exclusions and references retain their printed order and parent chains.')]
}
