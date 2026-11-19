"""Handwritten witnesses for the selected committee and authorship lists."""

COMMITTEES = 'pboc-committees-p002-003'
ASSIGNMENTS = """
11 组长：陆磊
12 成员（以姓氏笔画为序）：王信、刘宏华、孙天琦、严芳、李斌、邹澜、张文红、周宇、孟辉、高飞、彭立峰、谢丹。
20 总纂：孙天琦、杨柳、孟辉、李敏波。
21 统稿：李敏波、王晓青、刘通、郭旻蕙。
23 综述：王晓青、吴诗涵、齐玉录。
24 第一章：吴诗涵、张筱钰、王开元、陈俊、王磊、毛奇正。
25 第二章：褚兆林。
26 第三章：季诗朋、梁爽、王薇琳、潘璐、于超。
27 第四章：禤沛生、廖述魁、刘旸、杨瑞雯、尹曌天、陈宇春、陈琳。
28 第五章：潘璐、范熙程、吴诗涵、吴文光、张美娟、王海纳、李泽耿、周泽宇、马靖杰、顾湘、李夏炎。
29 专栏一：蔡大鹏。
30 专栏二：沈昶烨、刘婵婵、曾志刚。
31 专栏三：刘生福。
32 专栏四：陈阳、高佳琳、李慧敏、蔡思颖。
33 专栏五：刘婕、张文卓、陈艳颜。
34 专栏六：赵晟江、计磊、陈艳颜。
35 专栏七：范熙程。
36 专栏八：金融监管总局法规司资本监管研究课题组。
37 专栏九：金融监管总局法规司信用风险课题组。
38 专栏十：胡小璠、郭旻蕙。
39 专栏十一：谢霏、梁爽、季诗朋。
40 专栏十二：胡飞。
41 专栏十三：王睿。
42 专栏十四：王宇婷。
43 专栏十五：丁洪涛、吴文光。
44 专栏十六：江南、潘璐。
45 专题一：张美娟。
46 专题二：阮鹏飞。
47 专题三：范熙程。
48 专题四：杨山。
49 附录：徐堂正、吴诗涵、李博、王薇琳、廖述魁、禤沛生、康学赟、赵朋飞。
50 其他参与写作人员（以姓氏笔画为序）：于明星、马军伟、王亮、王大波、刘腾阳、纪宝林、邱彦华、张国文、赵伟欣、雷梦菲。
"""
entries = {9: 'H2|中国人民银行金融稳定分析小组', 14: 'H2|《中国金融稳定报告2024》指导小组',
           16: 'P|陆磊、肖远企、王建军、廖岷。', 18: 'H2|《中国金融稳定报告2024》编写组', 22: 'I|执笔'}
REVIEW_SOURCE_OVERRIDES = {}
for row in ASSIGNMENTS.strip().splitlines():
    location, wording = row.split(' ', 1)
    line = int(location)
    entries[line] = 'F|' + wording
    in_authorship = 23 <= line <= 49
    REVIEW_SOURCE_OVERRIDES[COMMITTEES, line] = {
        'source_kind': 'item', 'parents': ['执笔'] if in_authorship else [],
        'field_parent_lines': [(22, '执笔')] if in_authorship else [],
    }

REVIEW_ASSERTIONS = {
    COMMITTEES: ('complex-pboc-stability-2024', [2, 3], [(9, 16), (18, 50)],
                 '\n'.join(f'{line}|{entries[line]}' for line in sorted(entries))),
}

BOND_TERMS = 'tencent-conditions-definitions-formulas-p102-107'
day_count = '“Day Count Fraction” means, in respect of the calculation of an amount for any period of time (the “Calculation Period”), such day count fraction as may be specified in these Conditions or the relevant Pricing Supplement and:'
formula = '([360 x (Y₂-Y₁)] + [30 x (M₂-M₁)] + (D₂-D₁)) / 360'
terms = """
1411|H1|TERMS AND CONDITIONS OF THE NOTES
1413|P|on or after the date~global form~Solely for the purpose~exclusive of the laws and regulations of Hong Kong, Macau and Taiwan
1415|H2|1. Introduction
1417|I|Tencent Holdings Limited~up to US$30,000,000,000~as may be increased
1418|I|Series~one or more tranches~inconsistency~Pricing Supplement shall prevail
1419|I|15 September 2025~DB Trustees (Hong Kong) Limited~10 April 2014~24 April 2015~1 April 2019~25 May 2020
1420|I|Agency Agreement~Deutsche Bank AG, Hong Kong Branch~Principal Paying Agent~Exchange Agent~Deutsche Bank Trust Company Americas~Deutsche Bank Luxembourg S.A.~CMU Lodging Agent~Transfer Agents~any one of them
1422|I|other than in relation to the determination of interest~Principal Paying Agent~held in the CMU Service~CMU Lodging Agent
1424|I|Bearer Notes~not exchangeable~No single tranche~not be sold in the United States or to U.S. persons~Specified Office
1425|I|summaries~subject to their detailed provisions~Couponholders~during normal business hours
1427|H2|2. Interpretation
1429|H3|(a) Definitions
1431|P|following expressions~following meanings
1433|I|2006 ISDA Definitions~updated as at the date of issue of the first Tranche~www.isda.org
1434|I|2021 ISDA Definitions~latest version~any successor Matrix~first Tranche
1435|I|Accrual Yield~relevant Pricing Supplement
1436|I|Additional Business Centre(s)~city or cities
1437|I|Additional Financial Centre(s)~city or cities
1438|I|Business Day~other than in Condition 3(g)~Registration and delivery of Note Certificates
1439|I|in euro~TARGET Settlement Day~each (if any) Additional Business Centre
1440|I|other than euro and Renminbi~Principal Financial Centre~each (if any) Additional Business Centre
1441|I|denominated in Renminbi only~other than a Sunday or a Saturday~in Hong Kong~not authorised or obligated
1442|I|Business Day Convention~if so specified~different meanings in relation to different dates
1443|I|Following Business Day Convention~first following day
1444|I|Modified Following Business Day Convention~unless that day falls in the next calendar month~first preceding day
1445|I|Preceding Business Day Convention~first preceding day
1446|I|FRN Convention~Floating Rate Convention~Eurodollar Convention~numerically corresponds~Specified Period~provided, however
1447|I|no such numerically corresponding day~last day which is a Business Day
1448|I|not a Business Day~first following day~unless~first preceding day
1449|I|if the preceding such date occurred on the last day~all subsequent such dates~specified number of months
1450|I|No Adjustment~shall not be adjusted
1451|I|Calculation Agent~Principal Paying Agent or such other Person~Rate(s) of Interest and Interest Amount(s)
1452|I|Calculation Amount~relevant Pricing Supplement
1453|I|Capital Stock~Preferred Shares~excluding any debt securities convertible or exchangeable
1454|I|CMU Service~Central Moneymarkets Unit Service~Hong Kong Monetary Authority
1455|I|Consolidated Affiliated Entity~International Financial Reporting Standards 10~other than IFRS~International Accounting Standards 27~Unless otherwise specified
1456|I|Controlled Entity~Subsidiary or a Consolidated Affiliated Entity
1457|I|Coupon Sheet~in respect of a Note
1458|I|Day Count Fraction~Calculation Period~Pricing Supplement
1459|I|Actual/Actual (ICMA)~if
1460|I|equal to or shorter than~actual number of days~divided by the product~Regular Periods in any year
1461|I|longer than one Regular Period~the sum of
1462|I|in which it begins~divided by the product~Regular Periods in any year
1463|I|next Regular Period~divided by the product~Regular Periods in any year
1464|I|Actual/365~Actual/Actual (ISDA)~leap year divided by 366~non-leap year divided by 365
1465|I|Actual/365 (Fixed)~divided by 365
1466|I|Actual/360~divided by 360
1476|I|D₁~first calendar day~unless such number would be 31~D1 will be 30
1477|I|D₂~immediately following the last day~31 and D1 is greater than 29~D2 will be 30
1487|I|D₁~first calendar day~unless such number would be 31~D1 will be 30
1488|I|D₂~immediately following the last day~unless such number would be 31~D2 will be 30
1498|I|D₁~last day of February~such number would be 31~D1 will be 30
1499|I|D₂~last day of February but not the Maturity Date~such number would be 31~D2 will be 30
1501|I|in each such case~including the first day~excluding the last day
1503|I|Early Redemption Amount (Triggering Event)~101 per cent.~or such other amount
1504|I|Early Redemption Amount (Tax)~principal amount or such other amount~relevant Pricing Supplement
1505|I|Early Termination Amount~principal amount or such other amount~these Conditions or the relevant Pricing Supplement
1506|I|Exchange Act~United States Securities Exchange Act of 1934~as amended
1507|I|Extraordinary Resolution~Trust Deed
1508|I|Final Redemption Amount~principal amount or such other amount~relevant Pricing Supplement
"""
bond_lines = {int(line): rest for row in terms.strip().splitlines() for line, rest in [row.split('|', 1)]}
for first, last, condition, convention in [
        (1467, 1477, '(v)', '“30/360”'), (1478, 1488, '(vi)', '“30E/360” or “Eurobond Basis”'),
        (1489, 1499, '(vii)', '“30E/360 (ISDA)”')]:
    wording = f'{condition} if {convention} is so specified, the number of days in the Calculation Period divided by 360, calculated on a formula basis as follows:'
    bond_lines[first] = 'I|' + wording
    bond_lines[first + 2] = 'I|Day Count Fraction = ' + formula
    bond_lines[first + 4] = 'I|where:'
    for offset, anchors in [(5, 'Y₁~the year~first day'), (6, 'Y₂~the year~immediately following the last day'),
                            (7, 'M₁~calendar month~first day'), (8, 'M₂~calendar month~immediately following the last day')]:
        bond_lines[first + offset] = 'I|' + anchors
    REVIEW_SOURCE_OVERRIDES[BOND_TERMS, first + 2] = {
        'representation': 'typed', 'typed_facts': [('', 'Day Count Fraction', formula, {})],
        'field_parent_lines': [(1458, day_count), (first, wording)], 'field_delimiter': '=',
    }

# Ordered list parents taken from the selected clauses, including the exceptional
# end-of-February conventions and the boundary at the next top-level definition.
for first, last, parent in [(1422, 1422, 1420), (1439, 1441, 1438), (1443, 1450, 1442),
        (1447, 1449, 1446), (1459, 1501, 1458), (1460, 1463, 1459), (1462, 1463, 1461),
        (1469, 1477, 1467), (1480, 1488, 1478), (1491, 1499, 1489)]:
    for line in bond_lines:
        if first <= line <= last:
            REVIEW_SOURCE_OVERRIDES.setdefault((BOND_TERMS, line), {}).setdefault('parent_lines', []).append(parent)
REVIEW_ASSERTIONS[BOND_TERMS] = (
    'complex-tencent-2025-bond-programme', [102, 103, 104, 105, 106, 107],
    [(1411, 1420), (1422, 1439), (1440, 1452), (1453, 1465), (1466, 1487), (1488, 1508)],
    '\n'.join(f'{line}|{bond_lines[line]}' for line in sorted(bond_lines)),
)

OVERVIEW = 'nvidia-business-overview-p018-019'
REVIEW_ASSERTIONS[OVERVIEW] = ('complex-nvidia-2025-annual', [18, 19], [(495, 532), (534, 556)], """
495|H2|BUSINESS OVERVIEW
497|P|114% year on year to $130.5 billion~Hopper architecture~Spectrum-X~75.0%~147% to $81.5 billion~147% to $2.94
499|H3|Fiscal 2025 Results
501|I|Revenue~$130.5 billion~up 114%.
502|I|Gross Margin~75.0%~up 2.3 points.
503|I|Operating Income~$81.5 billion~up 147%.
504|I|Diluted Earnings Per Share~$2.94~up 147%.
506|H3|Fiscal 2025 Reportable Segments
508|P|two reportable segments~Compute & Networking~Graphics
510|I|Compute & Networking~$116.2 billion~up 145%~$82.9 billion~up 159%.
511|I|Graphics~$14.3 billion~up 6%~$5.1 billion~down 13%.
512|I|All Other*~Revenue: —~$(6.5) billion~up 33%.
513|I|Consolidated~$130.5 billion~up 114%~$81.5 billion~up 147%.
515|I|expenses not assigned~Compute & Networking or Graphics
517|H3|Fiscal 2025 Market Platforms
519|P|four large markets
521|I|Data Center
522|C|Data Center
523|I|Revenue: $115.2 billion~up 142%.
524|I|Gaming
525|C|Gaming
526|I|Revenue: $11.4 billion~up 9%.
527|I|Professional Visualization
528|C|Professional Visualization
529|I|Revenue: $1.9 billion~up 21%.
530|I|Automotive
531|C|Automotive
532|I|Revenue: $1.7 billion~up 55%.
534|H3|Business Highlights
536|I|NVIDIA Blackwell~agentic and reasoning AI applications
537|I|NVIDIA NIMs~AI Blueprints~Nemotron~Accenture
538|I|NVIDIA Ethernet for AI revenue~Spectrum-X~NVLink
539|I|GeForce RTX 50 Series~NVIDIA Blackwell~gamers, creators, and developers
540|I|$1.7 billion~up 55%~NVIDIA DRIVE~expected to begin in Fiscal 2026
541|I|Omniverse Cloud APIs~NIMs~digital twins and simulation workflows
542|I|Project GR00T~Cosmos~physical AI and robotics
544|H3|Fiscal 2025 Shareholder Returns
546|H4|Total Shareholder Return (TSR)*
548|C|Total Shareholder Return (TSR)
550|P|dividends reinvested~$142.62~January 24, 2025~last trading day~Nasdaq
552|H4|Return of Capital to Shareholders (in billions)
554|C|Return of Capital to Shareholders (in billions)
556|P|Form 10-K~Fiscal 2025
""")
for line, metric, value, qualifiers, change in [
        (501, 'Revenue', '$130.5 billion', {}, 'up 114%.'), (502, 'Gross Margin', '75.0', {'unit': '%'}, 'up 2.3 points.'),
        (503, 'Operating Income', '$81.5 billion', {}, 'up 147%.'),
        (504, 'Diluted Earnings Per Share', '2.94', {'unit': '$'}, 'up 147%.')]:
    REVIEW_SOURCE_OVERRIDES[OVERVIEW, line] = {
        'representation': 'typed', 'typed_facts': [('', metric, value, qualifiers), ('', 'year on year', change, {})],
        'sibling_axes': {'year on year': ('measure', metric)},
    }
for line, name, revenue, revenue_change, income, income_change in [
        (510, 'Compute & Networking', '$116.2 billion', 'up 145%', '$82.9 billion', 'up 159%.'),
        (511, 'Graphics', '$14.3 billion', 'up 6%', '$5.1 billion', 'down 13%.'),
        (512, 'All Other*', '—', None, '$(6.5) billion', 'up 33%.'),
        (513, 'Consolidated', '$130.5 billion', 'up 114%', '$81.5 billion', 'up 147%.')]:
    fields = [('Segment', name), ('Revenue', revenue)]
    if revenue_change:
        fields.append(('Revenue year on year', revenue_change))
    fields += [('Operating Income (Loss)', income), ('Operating Income (Loss) year on year', income_change)]
    REVIEW_SOURCE_OVERRIDES[OVERVIEW, line] = {'representation': 'typed',
        'typed_facts': [('', label, amount, {}) for label, amount in fields],
        'sibling_axes': {label: ('category', 'Segment', name) for label, _ in fields if label != 'Segment'}}
for line, name, revenue, change in [(521, 'Data Center', '$115.2 billion', 'up 142%.'),
        (524, 'Gaming', '$11.4 billion', 'up 9%.'), (527, 'Professional Visualization', '$1.9 billion', 'up 21%.'),
        (530, 'Automotive', '$1.7 billion', 'up 55%.')]:
    REVIEW_SOURCE_OVERRIDES[OVERVIEW, line + 1] = {'parents': [name], 'caption_parent': (line, name)}
    REVIEW_SOURCE_OVERRIDES[OVERVIEW, line + 2] = {'parents': [name], 'representation': 'typed',
        'typed_facts': [('', 'Revenue', revenue, {}), ('', 'year on year', change, {})],
        'field_parent_lines': [(line, name)], 'sibling_axes': {'year on year': ('measure', 'Revenue')}}

RISK = 'hkex-risk-committee-p112-117'
risk_text = """
3445|H2|Risk Committee Report
3447|H3|Risk Statement
3449|P|Effective risk management~risk appetite tolerances set by the Board
3451|P|global markets~protecting its reputation
3453|P|sufficient capital and liquidity~negative impact on stakeholders
3455|H3|The Risk Committee
3457|P|delegated by the Board~Annual Report
3459|C|照片
3461|H4|Summary of Work in 2024/2025
3463|I|Approved~new Group Financial Risk Management Policy
3464|I|Approved~Group Cyber Risk Management Policy~Group Incident Management Guidance
3465|I|Approved~Risk Assessment Matrix
3466|I|Approved~withdrawal limit~excess cash collateral~other currencies~HKEX clearing houses
3467|I|Approved~Terms of Reference~Executive Risk Committee~Clearing Risk Committee
3468|I|Endorsed~Risk Committee’s ToR~assessed
3469|I|Endorsed~Group Risk Appetite Statement
3470|I|Reviewed~Severe Weather Trading
3471|I|Reviewed~CrowdStrike Windows global IT outage
3472|I|Reviewed~daily settlement price methodology in HKCC
3473|I|Reviewed~Clearing Risk Committee reports
3474|I|Reviewed~geopolitical risk remediation~Risk Management Policy into a framework
3475|I|Reviewed~quarterly Group Risk Management~clearing house liquidity and capital adequacy
3476|I|Reviewed~management confirmation~adequacy and effectiveness
3478|P|adequate and effective risk management and internal control system~achieving its strategic objectives
3480|H3|Risk Governance
3482|P|Three Lines of Defence~Executive Risk Committee (ERiC)
3484|P|delegated by the Management Committee~discussion and handling when necessary
3486|C|Risk Governance
3488|H3|Group Risk Management
3490|P|approved by the Risk Committee~Group Risk Management Framework
3492|C|Group Risk Management
3494|H3|Principal Risks
3496|P|principal risks and uncertainties~if not properly~addressing the following principal risks
3583|P|climate-related risks~2024 Sustainability Report
3585|P|CHOW WOO Mo Fong, Susan
3587|P|Chairman of the Risk Committee
3589|P|Hong Kong, 19 February 2025
"""
risk_lines = {int(line): rest for row in risk_text.strip().splitlines() for line, rest in [row.split('|', 1)]}
for first, name, description, mitigations in [
        (3498, 'Strategic Risk', 'material adverse changes', ['global exchange industry trends', 'global and local changes in regulations', 'strategic flexibility', 'impacts of sanctions']),
        (3505, 'Model Risk', 'adverse consequences', ['Model Risk Governance Framework', 'internal and external model validation', 'Model Risk System']),
        (3511, 'Market Risk', 'adverse movements in market rates', ['Backtesting of margin and collateral', 'collateral management and margin collection', 'expected uncollateralised loss']),
        (3517, 'Treasury Investment Risk', 'Group’s treasury activities', ['investment and risk policies', 'market risk stress loss limit', 'FX and bond investment risk control dashboard']),
        (3523, 'Credit Risk', 'counterparty will not settle an obligation', ['Default management and recovery procedures', 'credit risk management function', 'collateral and margin deposits', 'counterparty defaulting']),
        (3530, 'Liquidity Risk', 'unable to settle obligations', ['Corporate Funds, Margin Funds', 'stress testing practices']),
        (3535, 'Cyber & Technology Risk', None, ['segregation of critical systems', 'testing and evaluation', 'Risk advice on strategic projects', 'Low latency', 'active capacity planning', 'NIST']),
        (3546, 'Third Party Risk', 'adversely impacted by third', ['Third Party Risk Management Policy', 'user awareness and knowledge', 'elevated third-party risk management requirements']),
        (3552, 'Data Risk', 'unexpected or underestimated', ['Group Data Governance Framework', 'Information Classification Standard', 'Data Community']),
        (3558, 'Human Capital Risk', 'not being able to retain key personnel', ['succession planning', 'attrition trends', 'strategic workforce planning']),
        (3564, 'Operational Risk', 'inability to provide services', ['Operational Risk Management Framework', 'evolving internal processes', 'Operational Risk Management tool', 'recover from business disruptions']),
        (3571, 'Legal Risk', 'unexpected or uncertain application', ['jurisdictions', 'external legal advice']),
        (3576, 'Compliance & Conduct Risk', 'incurring penalties', ['Group Compliance Policies', 'regular and targeted training', 'compliance policies monitoring'])]:
    risk_lines[first] = 'I|Principal Risk: ' + name
    REVIEW_SOURCE_OVERRIDES[RISK, first] = {'representation': 'typed', 'typed_facts': [('', 'Principal Risk', name, {})]}
    if description:
        risk_lines[first+1] = 'I|Description:~' + description
        REVIEW_SOURCE_OVERRIDES[RISK, first+1] = {'parent_lines': [first]}
        children = ['Key Mitigations', *mitigations]
        start = first + 2
    else:
        children = ['Description', 'due to cyber incidents', 'due to technology failures', 'Key Mitigations', *mitigations]
        start = first + 1
    for offset, word in enumerate(children):
        line = start + offset
        risk_lines[line] = 'I|' + word
        if word in {'Key Mitigations', 'Description'}:
            subheading = line
        REVIEW_SOURCE_OVERRIDES[RISK, line] = {'parent_lines': [first] if line == subheading else [first, subheading],
                                              'typed_parent_line': (first, name)}
REVIEW_ASSERTIONS[RISK] = ('complex-hkex-2024-annual', list(range(112, 118)),
    [(3445, 3459), (3461, 3478), (3480, 3492), (3494, 3534), (3535, 3563), (3564, 3589)],
    '\n'.join(f'{line}|{risk_lines[line]}' for line in sorted(risk_lines)))
