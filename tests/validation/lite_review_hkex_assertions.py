"""Third-batch HKEX/Ping An source assertions, authored from selected text.

These declarations precede production compilation and are never runtime input.
P/I records require complete ordered content; captions assert printed text only.
Simple explicitly labelled records may use either exact typed fields or the
complete content representation under the existing independently tested policy.
"""

REVIEW_ASSERTIONS = {
    'hkex-chairman-statement-p017-020': ('complex-hkex-2024-annual', [17, 18, 19, 20],
        [(334, 336), (338, 360), (362, 382), (384, 410)], '''
334|H2|Chairman’s Statement
336|C|Chairman’s Statement
338|P|2024~robust year~new leadership~strategic initiatives~region’s capital markets
340|P|2024~record trading activity~global competitiveness~connectivity, innovation and sustainability~sustained growth
342|H3|Our Performance
344|P|Whilst market volatility continued~positive global economic outlook~all our markets in 2024
346|P|Cash, Derivatives, ETP~Northbound and Southbound Stock Connect~three times~late September and early October 2024~Mainland China~Northbound Bond Connect~number of investors
348|P|71 new listings~$88.0 billion~4th globally~second half~China monetary and fiscal measures~LME~base metals
350|P|year ended 31 December 2024~$22.4 billion~up 9 per cent from 2023~$13.1 billion~up 10 per cent from 2023
352|H3|Dividend
354|P|second interim dividend~$4.90 per share~wholly in cash~$4.36 per share~September 2024~full-year dividend of $9.26 per share
356|H3|Strategic Update
358|P|2024~China Strength~global and regional connectivity~technological capabilities~eligible ETFs~Connect programmes~multi-year infrastructure~LME’s global metals warehousing network into Hong Kong
360|P|futureproofing~gateway between China and the world~Asia’s premier international financial centre
362|H3|Market Quality and Sustainability
364|P|market efficiency and quality~long-term sustainable development~well-regulated, efficient and transparent~international standards
366|P|remain open during severe weather~multi-year modernisation~faster and more efficient post-trade~first half of 2025~suitable stock settlement cycle
368|P|new treasury share regime~ISSB Climate Standards~eliminate single gender boards~risk management and internal controls~paperless listing~price discovery~SFC~SPAC companies and De-SPAC transactions
370|P|white paper in September 2024~transparency and price competition~working groups~second half of 2025~subject to a market consultation~first quarter of 2025~regulatory approvals
372|P|consultation in May 2024~mandate emissions reporting~LME-listed aluminium brands~EU CBAM~15 June 2025~responsible sourcing and LMEpassport
374|P|2024~Chief Executive Officer’s Review and Business Review~Annual Report
376|H3|Corporate Responsibility
378|P|corporate governance and ESG stewardship~market operator, regulator and a listed company~best-in-class governance~wider communities
380|P|2024~HKEX~OTC Clear, the LME and LME Clear~all four boards operate effectively~areas for enhancement
382|P|carbon neutrality goal by 2024~science-based greenhouse gas emission reduction targets~SBTi~for validation~Supporting the prosperity of all
384|P|HKEX Foundation~$86 million in 2024~financial literacy, diversity and inclusion, poverty relief and environmental sustainability~review of HKEX’s philanthropy strategy
386|P|LME~The Impact Facility~multi-year project~child labour in African mining communities~responsible mining practices
388|P|2024~employees~diversity and wellness~integrity, responsibility and transparency~risk management~regular training and education
390|P|2024 Sustainability Report~HKEX Group website~Annual Report
392|H3|Outlook
394|P|2025~monetary and trade policies~geopolitical developments~climate change~technological innovation~challenges and opportunities
396|P|customers, regulators and other stakeholders~connecting investors, corporates and markets~global financial community
398|H3|Acknowledgements
400|P|first HKEX Annual Report as Chairman~Mrs Laura M Cha~Board Senior Advisor~past year
402|P|International Advisory Council and Mainland China Advisory Group~Mr Peter Yan~October 2024~Mr Apurv Bagri and Ms Nisa Leung~after the conclusion of the 2025 AGM
404|P|Shareholders~Ms Bonnie Y Chan~chief executive officer~2024~HKEX Group
406|P|Carlson TONG
408|P|Chairman
410|P|Hong Kong, 27 February 2025
'''),
    'hkex-contents-p003': ('complex-hkex-2024-annual', [3], [(11, 56)], '''
11|H2|Contents
13|H3|Overview
15|I|Strategic and Financial Highlights: 04
16|I|Chairman’s Statement: 15
17|I|Chief Executive Officer’s Review: 19
19|H3|Organisation
21|I|Board and Committees: 28
22|I|Board of Directors and Senior Management: 30
23|I|Management Committee: 41
25|H3|Management Discussion and Analysis
27|I|Business Review: 44
28|I|Financial Review: 72
29|I|10-Year Financial Statistics: 79
31|H3|Governance
33|I|Corporate Governance Report: 82
34|I|Nomination and Governance Committee Report: 103
35|I|Audit Committee Report: 107
36|I|Risk Committee Report: 110
37|I|Remuneration Committee Report: 116
38|I|Corporate Responsibility Committee Report: 125
39|I|Directors’ Report: 127
41|H3|Financials
43|I|Auditor’s Report: 135
44|I|Consolidated Income Statement: 140
45|I|Consolidated Statement of Comprehensive Income: 141
46|I|Consolidated Statement of Financial Position: 142
47|I|Consolidated Statement of Changes in Equity: 143
48|I|Consolidated Statement of Cash Flows: 144
49|I|Notes to the Consolidated Financial Statements: 145
51|H3|Others
53|I|Shareholder Information: 231
54|I|Glossary: 234
56|P|Financial figures~HKD~unless otherwise stated
'''),
    'hkex-strategic-message-p007': ('complex-hkex-2024-annual', [7], [(66, 76)], '''
66|H2|Strategic and Financial Highlights
68|P|2024~market microstructure and listing franchise~multi-year platform development~diverse product ecosystem~new adjacent businesses~international engagement~third quarter~prudent cost management~highest-ever annual revenue and profit
70|P|2025~geopolitical and macroeconomic~likely~Mainland China~interest rate cuts~fundraising and secondary markets
72|P|25th anniversary~our listing this year~future-ready capabilities~long-term vibrancy, resilience, and sustainability~stakeholders
74|P|Bonnie Y Chan
76|P|Chief Executive Officer
'''),
    'hkex-operational-timeline-p008-009': ('complex-hkex-2024-annual', [8, 9], [(78, 117), (119, 143)], '''
78|H2|Strategic and Operational Highlights
80|C|照片
82|H3|Corporate
84|I|1 Mar: New Chief Executive Officer, Ms Bonnie Y Chan, appointed
85|I|3 May: New Chairman, Mr Carlson Tong, appointed
86|I|30 Oct: Plan to open office in Riyadh in 2025 announced
87|I|18 Nov: 10th anniversary of Stock Connect
89|H3|Regulation
91|I|19 Apr: Consultation conclusions~Climate-related Disclosures~Listing Rules amendments effective from 1 January 2025
92|I|11 Jun: Revised Listing Rules relating to Treasury Shares took effect
93|I|19 Dec: Consultation conclusions on Review of Corporate Governance Code and Related Listing Rules~effective from 1 July 2025
94|I|19 Dec: Consultation paper~Optimise IPO Price Discovery and Open Market Requirements~published
96|H3|Products and Services
98|I|29 Feb: First batch of Covered Call ETFs listed
99|I|29 Mar: All currency futures and options contracts included in Derivatives Holiday Trading
100|I|30 Apr: Asia’s first Spot Virtual Asset ETFs listed
101|I|13 Jun: First listing under Chapter 18C Specialist Technology Companies listing chapter
102|I|22 Jul: Eligibility criteria for ETFs under Stock Connect further relaxed
103|I|23 Jul: First inverse bitcoin exchange traded product listed
104|I|2 Sep: Weekly Hang Seng TECH Index Options launched
105|I|2 Sep: OTC Clear~new trades~Swap Connect on Special Working Days
106|I|4 Nov: Weekly Stock Options launched
107|I|15 Nov: HKEX Virtual Asset Index Series launched
108|I|21 Nov: Hang Seng HKEX Stock Connect China Enterprises Index~Hang Seng Indexes Company Limited
109|I|13 Dec: Fund Repository on the Integrated Fund Platform launched
110|I|18 Dec: HKEX Data Marketplace, a new web-based data platform, launched
112|H3|Market Operations
114|I|1 Jan: The LME and LME Clear~average trading and clearing fee increment of 13 per cent
115|I|22 Jan: The LME implemented New Closing Price methodology in phases
116|I|23 Mar: Self-Match Prevention service in Cash Market introduced
117|I|18 Apr: In-house development of the Orion Derivatives Platform announced
119|C|照片
121|I|20 May: New product features and services to Swap Connect introduced
122|I|27 Jun: The LME~explore Hong Kong as a Delivery Point~subsequently approved in January 2025
123|I|29 Jul: The LME approved Jeddah in Saudi Arabia as a Delivery Point for copper and zinc
124|I|31 Jul: Enhancements to Self-Match Prevention service in Derivatives Market introduced
125|I|4 Sep: The LME~White Paper on Enhancing Liquidity~transparency~price competition
126|I|23 Sep: Severe Weather Trading arrangements implemented in the Securities and Derivatives Markets
127|I|7 Oct: The UK Court of Appeal dismissed the appeal~LME and LME Clear~nickel market in 2022~January 2025~Supreme Court refused permission~end to the judicial review proceedings
128|I|18 Oct: Enhanced Application Timeframe~new listing application process~SFC
129|I|12 Dec: Announcement~multi-year post-trade services enhancement~Securities Market~Orion Cash Platform
130|I|16 Dec: OTC Clear~China Government Bonds and Policy Bank Bonds held through Bond Connect~Northbound Swap Connect~effective from 13 January 2025
131|I|17 Dec: Consultation conclusions~Minimum Spreads~phase 1~around mid-2025
132|I|18 Dec: LME Clear~default fund, initial margin~new margin type
134|H3|Sustainability
136|I|3 Jul: 2024 HKEX Impact Funding Scheme launched
137|I|1 Aug: Gold Standard’s Verified Emission Reductions introduced on Core Climate
138|I|6 Aug: Established a new Executive Corporate Responsibility Committee
139|I|23 Sep: 2024 HKEX Charity Partnership Programme launched
140|I|30 Sep: The LME~proposal to mandate emissions reporting~LME-listed aluminium brands~EU CBAM methodology~effective from 15 June 2025
141|I|1 Oct: HKEX Sustainability function launched
142|I|18 Dec: Provided carbon credits settlement services for Cathay Pacific Airways on Core Climate
143|I|31 Dec: Achieved carbon neutrality~HKEX’s operations~submitted emissions reduction targets~Science Based Targets initiative
'''),
    'hkex-independent-auditor-p137-141': ('complex-hkex-2024-annual', [137, 138, 139, 140, 141],
        [(4258, 4298), (4300, 4329), (4331, 4350), (4352, 4372), (4374, 4395)], '''
4258|H2|Auditor’s Report
4260|H3|Independent Auditor’s Report to the Members of Hong Kong Exchanges and Clearing Limited
4262|P|(incorporated in Hong Kong with limited liability)
4264|H3|Opinion
4266|H4|What we have audited
4268|P|Hong Kong Exchanges and Clearing Limited~Company~subsidiaries~Group~pages 140 to 230~comprise:
4270|I|consolidated statement of financial position as at 31 December 2024
4271|I|consolidated income statement for the year then ended
4272|I|consolidated statement of comprehensive income for the year then ended
4273|I|consolidated statement of changes in equity for the year then ended
4274|I|consolidated statement of cash flows for the year then ended
4275|I|notes~material accounting policy information~other explanatory information
4277|H4|Our opinion
4279|P|true and fair view~31 December 2024~financial performance~cash flows~year then ended~HKFRSs~HKICPA~Hong Kong Companies Ordinance
4281|H3|Basis for Opinion
4283|P|Hong Kong Standards on Auditing~HKSAs~HKICPA~Auditor’s Responsibilities~section of our report
4285|P|audit evidence~sufficient and appropriate~basis for our opinion
4287|H4|Independence
4289|P|independent of the Group~Code of Ethics for Professional Accountants~fulfilled our other ethical responsibilities
4291|H3|Key Audit Matters
4293|P|professional judgement~most significance~current period~as a whole~do not provide a separate opinion
4295|P|Key audit matters identified in our audit are summarised as follows:
4297|I|Goodwill impairment assessment
4298|I|Control environment supporting key information technology systems
4300|H4|Goodwill impairment assessment
4302|H5|Nature of the Key Audit Matter
4304|P|31 December 2024~HK$13,297 million~HK$13,192 million~LME Holdings Limited~Cash Generating Unit~Commodities
4306|P|goodwill~LME Group~significant judgements~impairment assessment~financial significance
4308|P|indefinite useful life~annually~more frequently if there is an indication for impairment
4310|P|recoverable amount~higher of the fair value less costs of disposal and value-in-use
4312|P|discounted cash flow model~next five years~projected revenue and operating expenditure~beyond the 5-year period~terminal growth rate~present values~discount rate
4314|P|no impairment~goodwill allocated to the Commodities segment
4316|P|significant assumptions~note 30~consolidated financial statements
4318|H5|How our audit addressed the Key Audit Matter
4320|P|procedures to evaluate~goodwill impairment assessment~following:
4322|I|Understanding of management’s process~estimation uncertainty~complexity, subjectivity, changes~management bias
4323|I|Assessing the appropriateness of the discounted cash flow model used
4324|I|reasonableness~revenue and operating expenditure~next five years~approved budgets, forecasts, future business plans~trading and clearing volumes
4325|I|reliability~budgets against actual results achieved in prior years
4326|I|terminal growth rate~discount rate~independent market data~valuation expert
4327|I|Independently performing sensitivity analysis~reasonably possible changes~goodwill impairment assessment
4329|P|available evidence~significant assumptions~supportable
4331|H4|Control environment supporting key information technology systems
4333|H5|Nature of the Key Audit Matter
4335|P|securities and derivatives trading, clearing and settlement~transactions and market data~depository, custody and nominee services fees~majority~completeness and accuracy~IT
4337|P|data capture, processing and reporting of fee revenue~core trading, clearing and settlement~financial accounting and reporting systems~key systems
4339|P|fee revenue~proper functioning~design and operating effectiveness~automated application controls~IT general controls~cybersecurity~logical access~automated calculations~information and system interfaces~program changes~computer operations~program development
4341|H5|How our audit addressed the Key Audit Matter
4343|P|end-to-end processes~key systems~transactions generating fee revenue~financial statements~design~manual and automated application controls~IT general controls~relied on
4345|P|revenue streams~high dependency on IT systems~following:
4347|I|IT governance framework, cybersecurity and IT incident management~throughout the audit~design and operating effectiveness~access to programs and data~program changes~computer operations~program development
4348|I|key automated application controls~capture, processing and reporting~logical access~automated calculations~information and system interfaces
4350|P|procedures performed~control environment~can be relied on~audit of revenue
4352|H3|Other Information
4354|P|directors~responsible~annual report~other than the consolidated financial statements and our auditor’s report
4356|P|opinion~does not cover the other information~do not express any form of assurance conclusion
4358|P|responsibility~read the other information~materially inconsistent~knowledge obtained in the audit~materially misstated
4360|P|If~material misstatement~required to report~nothing to report
4362|H3|Responsibilities of Directors for the Consolidated Financial Statements
4364|P|directors~true and fair view~HKFRSs~HKICPA~Companies Ordinance~internal control~free from material misstatement~fraud or error
4366|P|going concern~unless~liquidate the Group~cease operations~no realistic alternative
4368|P|Audit Committee~assists the directors~overseeing~financial reporting process
4370|H3|Auditor’s Responsibilities for the Audit of the Consolidated Financial Statements
4372|P|reasonable assurance~as a whole~fraud or error~solely to you, as a body~Section 405~no other purpose~do not assume responsibility~not a guarantee~individually or in the aggregate~economic decisions
4374|P|HKSAs~professional judgement~professional scepticism~We also:
4376|I|Identify and assess~fraud or error~sufficient and appropriate~risk of not detecting~fraud is higher~collusion, forgery, intentional omissions, misrepresentations~override of internal control
4377|I|internal control~design audit procedures~not for the purpose of expressing an opinion~effectiveness
4378|I|appropriateness of accounting policies~reasonableness of accounting estimates~disclosures~directors
4379|I|going concern~material uncertainty~If~draw attention~inadequate~modify our opinion~up to the date~future events~cease to continue
4380|I|overall presentation, structure and content~underlying transactions and events~fair presentation
4381|I|group audit~sufficient appropriate audit evidence~entities or business units~direction, supervision and review~solely responsible~audit opinion
4383|P|Audit Committee~planned scope and timing~significant audit findings~significant deficiencies~internal control
4385|P|Audit Committee~ethical requirements~independence~relationships~eliminate threats or safeguards applied
4387|P|most significance~current period~key audit matters~unless law or regulation precludes public disclosure~extremely rare circumstances~adverse consequences~public interest benefits
4389|P|engagement partner~Peter Po-ting Li
4391|P|PricewaterhouseCoopers
4393|P|Certified Public Accountants
4395|P|Hong Kong, 27 February 2025
'''),
    'hkex-nomination-governance-p105-108': ('complex-hkex-2024-annual', [105, 106, 107, 108],
        [(3219, 3251), (3253, 3273), (3275, 3312), (3314, 3350)], '''
3219|H2|Nomination and Governance Committee Report
3221|H3|The Nomination and Governance Committee
3223|P|NGC~authority by the Board~composition and diversity~nominating Board candidates~appointment of Directors~INED’s independence and commitment~succession planning~leadership training~corporate governance~website OS
3225|P|five INEDs~four meetings in 2024~attendance records~Corporate Governance Report
3227|H4|Summary of Work in 2024/2025
3229|I|internally led evaluations~HKEX, OTC Clear, the LME and LME Clear~respective governance committees
3230|I|composition of the Board and its committees
3231|I|Board candidates~election or re-election~Shareholders at AGMs
3232|I|appointment of Directors~Board committees
3233|I|independence of the INEDs
3234|I|external appointment(s) of Director(s)
3235|I|time commitment~performance of their responsibilities
3236|I|succession planning~Board and senior executives
3237|I|NGC’s terms of reference
3238|I|training and continued professional development~Directors and Senior Management
3239|I|annual Corporate Governance Report
3241|H3|Changes in Non-executive Directors during 2024
3243|P|February 2024~Chan Kin Por and Peter Yan~re-appointed Susan Chow~approximately two years~2024 AGM~AGM in 2026
3245|P|2024 AGM~Nicholas Allen, Anna Cheung and Zhang Yichen~re-elected~three years~24 April 2024~AGM in 2027
3247|P|Peter Yan’s resignation~28 October 2024~Herbert Chia~29 October 2024~AGM in 2026
3249|H3|Board Composition and Diversity
3251|P|Since 2013~Board Diversity Policy~at least four female Directors~31 per cent~at least the current level~long-term goal~independent professional search firm~as and when appropriate~over time
3253|P|Nomination Policy~non-exhaustive list~maximum tenure of nine consecutive years~Non-executive Directors~re-election~website CG
3255|P|During 2024~structure, size, and diversity~Nomination Policy~Board Diversity Policy~Main Board Listing Rules~Directors’ skills matrix~Board Composition
3257|H3|Nomination of Candidate
3259|P|Carlson Tong, Nisa Leung and Joseph Yam~Government Appointed Directors~Apurv Bagri~Elected Director~2025 AGM~nine consecutive years~not eligible~retire
3261|P|20 February 2025~re-appointed Carlson Tong and Joseph Yam~appointed Ding Chen~approximately two years~30 April 2025~AGM to be held in 2027
3263|P|During 2024~independent professional search firm~current composition~skills matrix~selection criteria~Nomination Policy~Board Diversity Policy
3265|P|21 October 2024~Peter Brien~2025 AGM~Nomination Policy~market knowledge and experience~integrity~including without limitation~gender, age, cultural and educational background, ethnicity, professional experience, skills and knowledge
3267|P|Mr Brien~capital markets~regulatory matters~appropriate Board candidate~2025 AGM~independence~Main Board Listing Rules
3269|P|Save as disclosed below~Mr Brien~does not hold any cross-directorships~nor~significant links
3271|P|Peter Brien~2024~chairman of Chinachem Group Holdings Limited~court appointed administrators~Joseph Yam~supervisory managing organisation~Nina and Teddy Wang Charitable Trust~Upon commencement~Trustee~ownership and oversight
3273|P|Mr Brien~does not have~service contracts~not determinable~within one year~without compensation~other than statutory compensation~circular~website IR
3275|H3|Board Independence
3277|P|Independent Directors~objective judgement~constructive challenge
3279|P|same set~Rule 3.13~upon appointment, annually~any other time~circumstances warrant reconsideration
3281|H4|Assessment upon Director’s Appointment
3283|I|Chan Kin Por and Peter Yan~April 2024~Herbert Chia~October 2024~independence confirmations
3285|H4|Ongoing Assessment
3287|I|Each INED~as soon as practicable~change~independence~No such notification~during 2024
3288|I|Director’s interests~pages 97 and 98~Annual Report
3290|P|26 February 2025~annual independence confirmation~each INED~Rule 3.13
3292|H4|Annual Assessment
3294|I|every NGC member abstained~his/her own independence
3295|I|Government Appointed Directors~Chan Kin Por~Executive Councillor and a Legislative Councillor~Joseph Yam~Executive Councillor~Government~Minority Controller
3296|I|all INEDs~free from any business or other relationship~discharge their duties effectively~all remained independent
3298|P|key features or mechanisms~Board and governance structure~independent views and input
3300|H4|Board and Committees’ Structure
3302|I|Since its listing~majority of Non-executive Directors~Chief Executive Officer~only Executive Director~remaining 12 Directors~Chairman~INEDs~not related~Senior Management
3303|I|all governance related committees~INEDs
3304|I|Separation~Chairman~Chief Executive Officer~balance of power and authority
3306|H4|Non-executive Directors’ Tenure
3308|I|maximum tenure of nine consecutive years~eligible for nomination~re-election
3310|H4|Non-executive Directors’ Remuneration
3312|I|fixed fee(s)~not entitled~Share Award Scheme~Remuneration Committee Report~note 15~Consolidated Financial Statements
3314|H4|Appointment of Non-executive Directors
3316|I|Independent professional search firm(s)~from time to time~Non-executive Directors
3317|I|qualification and time commitment~Board’s composition~skills matrix~criteria approved by the Board~Nomination Policy~Board Diversity Policy
3319|H4|Annual Review of Non-executive Directors’ Commitment and Independence
3321|I|annually~time commitment~2024~Board Process~Directors’ Time Commitment
3322|I|independence~upon appointment, annually~circumstances warrant reconsideration
3324|H4|Conflict Management
3326|I|Guidelines on Conduct~Director’s Handbook~avoiding conflicts of interest~director in conflict~Corporate Governance Report
3328|H4|Professional Advice
3330|I|all Directors~Group Company Secretary~in-house legal team~independent professional advisers~Company’s expense
3332|H4|Board Evaluation
3334|I|quality and efficiency~annual evaluation~Board Effectiveness
3336|H3|Directors’ Time Commitment
3338|P|sufficient time and attention~number and nature of offices~significant commitments~appointment~subsequent changes~timely manner
3340|P|26 February 2025~during 2024~each Director~sufficient time and attention~responsibilities effectively~following:
3342|I|Directors’ skills and experience~skills matrix~Board Composition
3343|I|role and positions at HKEX and its subsidiaries~external directorships or offices~other major commitments
3344|I|attendance record~board and committee meetings~Board Process~subsidiaries~during the year
3346|P|Carlson TONG
3348|P|Chairman of the Nomination and Governance Committee
3350|P|Hong Kong, 26 February 2025
'''),
    'pingan-chairman-p014-019': ('complex-pingan-2024-annual', [14, 15, 16, 17, 18, 19],
        [(502, 508), (510, 510), (512, 520), (522, 528), (530, 540), (542, 550), (552, 552), (554, 564)], '''
502|H2|Chairman’s Statement
504|P|future is already here~integrity~innovation~artificial intelligence~Chinese modernization~not about how to adapt~become the change itself~ride it and shape its direction
506|P|2024~75th anniversary~Third Plenary Session~20th Central Committee~long-term economic outlook~lackluster domestic demand~short and medium term~people-centered~integrated finance~health and senior care~risk management and investment~digital transformation~steady progress, innovation-driven growth, and outstanding resilience
508|P|9.1%~RMB121,862 million~47.8%~RMB126,607 million~RMB1,028,925 million~12.6%~13 consecutive years~RMB1.62 per share~2024~RMB2.55 per share~5%~37.9%~Life & Health NBV~28.8%~NBV per agent~43.3%~5.8%~2.2 pps
510|P|worry-free, time-saving, and money-saving~troublesome, time-consuming, and costly~supply-demand imbalances~lack of standards~inconsistent service levels~love and responsibility~complex and cumbersome~mental and physical energy~traditional financial, health and senior care~largest proportions~cost of living
512|P|making life easier with expertise~people-centered~AI~one customer, multiple accounts, multiple products, and one-stop services~financial advisers, family doctors, and senior care concierges~cutting costs~optimizing resource allocation
514|C|Photograph
516|P|patient~medical concierge~Ping An Health Insurance~medical visit
518|P|three key numbers~242 million~December 31, 2024~25.6%~four or more contracts~98.0%~32.07 million~9.8%~over 7,000 outlets in 330 cities~over 1.30 million~approximately 290 million~over 170 million~nearly 236 million
520|P|Life & Health~26.5%~43.3%~363 thousand~December 31, 2024~13-month~3.6 pps~25-month~3.9 pps~6.0%~2.4 pps~2024
522|P|Ping An P&C~4.7%~RMB328,146 million~67.7%~RMB15,021 million~98.3%~2.3 pps~98.1%~Ping An Bank~RMB44,508 million~1.06%~250.71%~December 31, 2024
524|P|insurance + health care~insurance, health care, investment and technology~retail financial customers and corporate clients~nearly 67,000~over 31 million~12 months ended December 31, 2024~over RMB140 billion~about 70%~Life’s NBV
526|P|finance + senior care services~insurance + home-based senior care~insurance + high-end senior care~Medical, Nursing, Housing, and Entertainment Alliances~over 150~75 cities~10-dimensional~December 31, 2024~Over 160,000~five cities~Shanghai and Shenzhen~second half of 2025
528|P|finance + health care services~over 21 million~2.1 pps higher than in 2023~nearly 79%~newly-enrolled~2024~commercial insurance + health care fund + health care service
530|P|online, in-store, in-home and in-company~about 50,000~all top 100 hospitals and 3A hospitals~December 31, 2024~PKU Healthcare Group~approximately RMB5.51 billion~2024
532|C|Illustration
534|P|3-level large model system~3 financial databases~5 health care databases~picture generated by Ping An’s text-to-image model
536|P|past decade~integrated finance + health and senior care~three-level large model~large speech models, large language models, large vision models~three financial databases and five health care databases~30 trillion bytes~85 scenarios
538|P|1.84 billion times~80%~2024~93%~within seconds~56%~Smart Quick Claim~4,000 times~10.4%~RMB11.94 billion
540|P|Ping An Doctor’s Home~Ping An Medical Master~12 AI-driven models~about 62%~over 2,000 diseases~99%~above 95%
542|P|autumn of 2024~Jiangmen, Guangdong~Hundred, Thousand, and Ten Thousand Project~Tanjiang River~406-year-old~RMB166 million~10,135~December 31, 2024~RMB124,712 million~RMB157,762 million~RMB58,608 million~RMB52,014 million~AA~No.1~Asia-Pacific~three consecutive years
544|C|Photograph
546|P|Chairman Ma Mingzhe~smart agriculture demonstration base~Jiangmen~Guangdong Province~September 12, 2024
548|P|2024~2025~final year~14th Five-Year Plan~15th Five-Year Plan~short- and medium-term~long-term outlook have not changed~financial, health and senior care
550|P|market trends~integrated finance + health and senior care~customer acquisition, activation, migration and retention~retail customers, contracts per customer and profit per customer~worry-free, time-saving, and money-saving
552|P|DeepSeek~Reform and innovation~2025 business policy~risks under control~five major systems~digital business, digital operations, digital management, digital marketing, and digital services~financial advisory, family doctor, and senior care concierge~online, in-store, in-home and in-company~driver~enabler
554|P|interest rate pivot moves downward~downward cycle of liabilities~assets and liabilities~macroeconomic cycles~long liability duration~strategic emerging industries, advanced manufacturing, next-generation infrastructure, and value-based assets~patient capital
556|P|Thunderstorms are normal~reform and innovation~2025~focusing on core businesses, boosting revenue and cutting costs, advancing reform and innovation, and preventing risks~dual-driver strategy~risk limits~technology finance, green finance, inclusive finance, pension finance, and digital finance~financial powerhouse
558|C|Signature
560|P|Chairman
562|P|Shenzhen, PRC
564|P|March 19, 2025
'''),
    'pingan-integrated-finance-p022-024': ('complex-pingan-2024-annual', [22, 23, 24],
        [(636, 650), (652, 680), (682, 720)], '''
636|H4|Strong online-merge-offline channel networks
638|P|over 7,000 outlets~330 cities~over 1.3 million~property and casualty insurance, life insurance~Jin Guan Jia, Ping An Pocket Bank, Ping An Auto Owner, and Ping An Health
640|H4|Robust ecosystem-based service capability
642|P|Nearly 63%~December 31, 2024~approximately 3.37 contracts~RMB59.9 thousand~per capita~1.6 times and 3.8 times~not entitled~respectively
644|H4|Strong technology platform capabilities
646|P|largest in Asia~approximately 1.84 billion times~80%~2024~quality, efficiency, and risk management~RMB11.94 billion~2024~diverse financial needs
648|H4|Highly synergistic organizational culture
650|P|One Ping An~value maximization~one customer, multiple accounts, multiple products, and one-stop services~customer development, risk management, investment, back-office centralization and operations, consumer rights protection, brand management, and the value system~number of retail customers, contracts per customer and profit per customer
652|H3|Results of Integrated Finance
654|P|all-around, full-lifecycle~contracts per customer~profit per customer~customer acquisition and operating cost advantages
656|H4|Growth Drivers
658|P|three key numbers~retail customers, contracts per customer, and profit per customer~242 million~December 31, 2024~2.92 contracts~RMB446.90~4.7%~2.2 times~2023~benign pressure~rising proportion of new customers~credit portfolio~existing high-value customers
660|C|Growth Drivers
662|P|Notes:
664|P|(1)~operating profits attributable to the shareholders of the parent company
666|P|(2)~current period and the same period last year~end-2024~long-run investment return assumption (4.0%)
668|P|(3)~may not match~rounding
670|H4|Higher Customer Retention
672|P|1.6 pps~90.9%~2024~continuous customer development
674|H5|Customers with longer tenures have higher retention rates
676|P|longer~higher~72.2%~five or more years~94.7%~32 pps~first-year customers
678|H5|Customer retention rates by tenure
680|C|Customer retention rates by tenure
682|H5|Customers with multiple products have higher retention rates
684|P|one customer, multiple accounts, multiple products, and one-stop services~four or more contracts~98.0%~11.5 pps~only one contract
686|H5|Customer retention rates by number of contracts
688|C|Customer retention rates by number of contracts
690|H4|Better Customer Growth
692|P|242 million~December 31, 2024~4.7%~beginning of 2024~32.07 million~9.8%~year on year
694|H5|Multiple Channels for Customer Acquisition
696|P|online-merge-offline~whole country~reaches and acquires customers efficiently
698|H6|Strong offline customer development and services
700|I|Offline life and P&C insurance and banking outlets: 7,000+.
701|I|Cities covered by offline outlets nationwide: 330.
702|I|Sales service team members for P&C and life insurance, etc.: 1.30 mn+.
704|H6|Abundant online user traffic
706|I|Registered users of “Ping An Jin Guan Jia” app: ~290 mn.
707|I|Registered users of “Ping An Pocket Bank” app: 170 mn+.
708|I|Registered users of “Ping An Auto Owner” app: ~236 mn.
710|H4|Deeper Product Penetration
712|P|diverse financial needs~products’ penetration~continuous growth in profit per customer
714|H5|Penetration rates of main products rise continuously
716|P|life and health insurance~property & casualty insurance~44.9% (up 2.2 pps year on year)~30.6% (up 0.5 pps year on year)~respectively~December 31, 2024
718|H5|Penetration rates of main products
720|C|Penetration rates of main products
'''),
    'pingan-mission-opportunities-p006-007': ('complex-pingan-2024-annual', [6, 7], [(215, 237), (239, 273)], '''
215|H2|Corporate Mission
217|H3|WHY WE’RE HERE
219|P|world-leading integrated finance, health and senior care services group~customers, employees, shareholders and society
221|P|customer pain points~worry-free, time-saving, and money-saving~Expertise makes life easier
223|P|market developments~technological advancements~worry-free, time-saving, and money-saving~meet their needs
225|H4|Worry-Free
227|P|one-stop integrated finance~24/7 online and offline health care~3-in-1~AI concierges, life concierges and doctor concierges~financial advisers, family doctors, and senior care concierges
229|H4|Time-Saving
231|P|online, in-store, in-home and in-company~One-stop products and one-click services~time and trouble
233|H4|Money-Saving
235|P|minimize costs~optimize risk management~maximize benefits~suitable products~claim solutions~service costs~cost-effective~benefits and loyalty points
237|C|Photograph
239|H2|Opportunities of Our Times
241|H3|WHY WE’RE HERE
243|P|medium-to-high speed growth~over 40 years~financial, health and senior care~market sizes and growth potential
245|P|intense competition~homogeneous offerings~service differentiation~supply shortages~lack of standards~inconsistent service levels~digital innovation
247|H4|The rise of the middle class and the diversification of their assets are fueling strong demand for integrated financial services
249|P|one-third~world’s middle class by 2030~not only~but also diversified assets~insurance policies, credit cards, bank accounts, wealth management products, vehicles and homes~wealth management, insurance protection and consumer finance
251|I|China’s middle class as a proportion of global middle class by 2030: 1/3.
253|H4|Growing health care demand and uneven resource distribution is driving the urgent need for efficient health care services
255|P|far lower than developed countries~RMB16 trillion by 2030~difficulty in seeing a doctor and the high cost~uneven resource distribution~low efficiency~one-stop~upgrade services and improve efficiency
257|I|Expected size of China’s health care market by 2030: RMB16 trn.
259|H4|Accelerating population aging and the evolving senior care pattern are driving long-term demand for high-quality senior care services
261|P|Over 20%~aged 65 and above by 2030~RMB30 trillion by 2035~10%~GDP~9073~90%~7%~3%~home-based~product and service model innovation, resource integration, and quality improvement
263|I|Expected size of China’s silver economy by 2035: RMB30 trn.
265|P|Notes:
267|P|(1)~expected percentage~middle class by 2030~Credit Suisse Research Institute
269|P|(2)~expected size~health care services market by 2030~Outline of the Healthy China 2030 Plan
271|P|(3)~expected size~silver economy by 2035~Blue Book on Silver Economy: Report on Development of China’s Silver Economy (2024)
273|C|Photograph
'''),
}

# These are explicit short label/value presentations in the source, not numeric
# conversions: dates, printed page numbers and quantities retain distinct roles.
REVIEW_TYPED_ASSERTIONS = {
    ('hkex-nomination-governance-p105-108', 3303): [
        ('Members of all governance related committees', 'be', 'INEDs', {'polarity': 'positive', 'tense': 'present'})],
    ('pingan-integrated-finance-p022-024', 700): [('', 'Offline life and P&C insurance and banking outlets', '7,000+.', {})],
    ('pingan-integrated-finance-p022-024', 701): [('', 'Cities covered by offline outlets nationwide', '330.', {})],
    ('pingan-integrated-finance-p022-024', 702): [('', 'Sales service team members for P&C and life insurance, etc.', '1.30 mn+.', {})],
    ('pingan-integrated-finance-p022-024', 706): [('', 'Registered users of “Ping An Jin Guan Jia” app', '~290 mn.', {})],
    ('pingan-integrated-finance-p022-024', 707): [('', 'Registered users of “Ping An Pocket Bank” app', '170 mn+.', {})],
    ('pingan-integrated-finance-p022-024', 708): [('', 'Registered users of “Ping An Auto Owner” app', '~236 mn.', {})],
    ('pingan-mission-opportunities-p006-007', 251): [('', 'China’s middle class as a proportion of global middle class by 2030', '1/3.', {})],
    ('pingan-mission-opportunities-p006-007', 257): [('', 'Expected size of China’s health care market by 2030', 'RMB16 trn.', {})],
    ('pingan-mission-opportunities-p006-007', 263): [('', 'Expected size of China’s silver economy by 2035', 'RMB30 trn.', {})],
}
REVIEW_REPRESENTATION_POLICIES = {key: 'either' for key in REVIEW_TYPED_ASSERTIONS}
REVIEW_REPRESENTATION_POLICIES[('hkex-nomination-governance-p105-108', 3303)] = 'typed'
REVIEW_SOURCE_OVERRIDES = {
    ('hkex-nomination-governance-p105-108', 3303): {'binding_qualifiers': {'tense': 'present'}},
}
REVIEW_REQUIRED_RELATIONS = {
    ('hkex-nomination-governance-p105-108', 3303): [{
        'type': 'narrative_prepositional_attachment',
        'left': {'preposition': 'of', 'semantic_role': 'complement',
                 'attachment': {'kind': 'nominal', 'head': 'Members'},
                 'complement': 'all governance related committees'},
        'right': {'subject': 'Members of all governance related committees', 'attribute': 'be',
                  'scope': ['Nomination and Governance Committee Report', 'Board Independence',
                            'Board and Committees’ Structure'], 'qualifiers': {'tense': 'present'}},
    }],
}

# All dated entries, rather than only currently recognised entries, are
# independently transcribed as explicit label/value alternatives. A date label
# is a literal record label, not an amount. Repeated dates remain separate source
# records, with different content under their printed category and position.
_TIMELINE_FIELDS = [
    (84, '1 Mar', 'New Chief Executive Officer, Ms Bonnie Y Chan, appointed'),
    (85, '3 May', 'New Chairman, Mr Carlson Tong, appointed'),
    (86, '30 Oct', 'Plan to open office in Riyadh in 2025 announced'),
    (87, '18 Nov', '10th anniversary of Stock Connect'),
    (91, '19 Apr', 'Consultation conclusions on Enhancement of Climate-related Disclosures under the Environmental, Social and Governance Framework published, with Listing Rules amendments effective from 1 January 2025'),
    (92, '11 Jun', 'Revised Listing Rules relating to Treasury Shares took effect'),
    (93, '19 Dec', 'Consultation conclusions on Review of Corporate Governance Code and Related Listing Rules published, with new requirements effective from 1 July 2025'),
    (94, '19 Dec', 'Consultation paper on Proposals to Optimise IPO Price Discovery and Open Market Requirements published'),
    (98, '29 Feb', 'First batch of Covered Call ETFs listed'),
    (99, '29 Mar', 'All currency futures and options contracts included in Derivatives Holiday Trading'),
    (100, '30 Apr', 'Asia’s first Spot Virtual Asset ETFs listed'),
    (101, '13 Jun', 'First listing under Chapter 18C Specialist Technology Companies listing chapter'),
    (102, '22 Jul', 'Eligibility criteria for ETFs under Stock Connect further relaxed'),
    (103, '23 Jul', 'First inverse bitcoin exchange traded product listed'),
    (104, '2 Sep', 'Weekly Hang Seng TECH Index Options launched'),
    (105, '2 Sep', 'OTC Clear started accepting new trades for clearing under Swap Connect on Special Working Days'),
    (106, '4 Nov', 'Weekly Stock Options launched'),
    (107, '15 Nov', 'HKEX Virtual Asset Index Series launched'),
    (108, '21 Nov', 'Hang Seng HKEX Stock Connect China Enterprises Index launched in collaboration with Hang Seng Indexes Company Limited'),
    (109, '13 Dec', 'Fund Repository on the Integrated Fund Platform launched'),
    (110, '18 Dec', 'HKEX Data Marketplace, a new web-based data platform, launched'),
    (114, '1 Jan', 'The LME and LME Clear implemented average trading and clearing fee increment of 13 per cent'),
    (115, '22 Jan', 'The LME implemented New Closing Price methodology in phases'),
    (116, '23 Mar', 'Self-Match Prevention service in Cash Market introduced'),
    (117, '18 Apr', 'In-house development of the Orion Derivatives Platform announced'),
    (121, '20 May', 'New product features and services to Swap Connect introduced'),
    (122, '27 Jun', 'The LME announced its intention to explore Hong Kong as a Delivery Point, which was subsequently approved in January 2025'),
    (123, '29 Jul', 'The LME approved Jeddah in Saudi Arabia as a Delivery Point for copper and zinc'),
    (124, '31 Jul', 'Enhancements to Self-Match Prevention service in Derivatives Market introduced'),
    (125, '4 Sep', 'The LME published the White Paper on Enhancing Liquidity, outlining a package of measures designed to boost transparency and increase price competition'),
    (126, '23 Sep', 'Severe Weather Trading arrangements implemented in the Securities and Derivatives Markets'),
    (127, '7 Oct', 'The UK Court of Appeal dismissed the appeal by the claimant against the LME and LME Clear in relation to the events in the nickel market in 2022. Subsequently in January 2025, the Supreme Court refused permission for the appellants to appeal further, effectively bringing an end to the judicial review proceedings'),
    (128, '18 Oct', 'Enhanced Application Timeframe for the new listing application process jointly announced with the SFC'),
    (129, '12 Dec', 'Announcement of a multi-year post-trade services enhancement programme for the Securities Market with new post-trade features and services progressively added to the Orion Cash Platform'),
    (130, '16 Dec', 'OTC Clear announced the acceptance of China Government Bonds and Policy Bank Bonds held through Bond Connect as collateral for Northbound Swap Connect effective from 13 January 2025'),
    (131, '17 Dec', 'Consultation conclusions on Proposed Reduction of Minimum Spreads in the Hong Kong Securities Market published, with the phase 1 of minimum spreads reduction implemented around mid-2025'),
    (132, '18 Dec', 'LME Clear implemented changes to its default fund, initial margin and added a new margin type'),
    (136, '3 Jul', '2024 HKEX Impact Funding Scheme launched'),
    (137, '1 Aug', 'Gold Standard’s Verified Emission Reductions introduced on Core Climate'),
    (138, '6 Aug', 'Established a new Executive Corporate Responsibility Committee'),
    (139, '23 Sep', '2024 HKEX Charity Partnership Programme launched'),
    (140, '30 Sep', 'The LME announced its proposal to mandate emissions reporting for LME-listed aluminium brands, in line with the EU CBAM methodology, effective from 15 June 2025'),
    (141, '1 Oct', 'HKEX Sustainability function launched'),
    (142, '18 Dec', 'Provided carbon credits settlement services for Cathay Pacific Airways on Core Climate'),
    (143, '31 Dec', 'Achieved carbon neutrality in HKEX’s operations and submitted emissions reduction targets to Science Based Targets initiative'),
]
for _line, _label, _value in _TIMELINE_FIELDS:
    _key = ('hkex-operational-timeline-p008-009', _line)
    REVIEW_TYPED_ASSERTIONS[_key] = [('', _label, _value, {})]
    REVIEW_REPRESENTATION_POLICIES[_key] = 'either'

# Original printed directory references: these are not quantities. The role
# requirement is substantive even if a generic content/field representation
# currently reports responsibility_complete. No candidate was consulted.
REVIEW_DIRECTORY_ASSERTIONS = {
    'hkex-contents-p003': [
        (15, 'Overview', 'Strategic and Financial Highlights', '04'),
        (16, 'Overview', 'Chairman’s Statement', '15'),
        (17, 'Overview', 'Chief Executive Officer’s Review', '19'),
        (21, 'Organisation', 'Board and Committees', '28'),
        (22, 'Organisation', 'Board of Directors and Senior Management', '30'),
        (23, 'Organisation', 'Management Committee', '41'),
        (27, 'Management Discussion and Analysis', 'Business Review', '44'),
        (28, 'Management Discussion and Analysis', 'Financial Review', '72'),
        (29, 'Management Discussion and Analysis', '10-Year Financial Statistics', '79'),
        (33, 'Governance', 'Corporate Governance Report', '82'),
        (34, 'Governance', 'Nomination and Governance Committee Report', '103'),
        (35, 'Governance', 'Audit Committee Report', '107'),
        (36, 'Governance', 'Risk Committee Report', '110'),
        (37, 'Governance', 'Remuneration Committee Report', '116'),
        (38, 'Governance', 'Corporate Responsibility Committee Report', '125'),
        (39, 'Governance', 'Directors’ Report', '127'),
        (43, 'Financials', 'Auditor’s Report', '135'),
        (44, 'Financials', 'Consolidated Income Statement', '140'),
        (45, 'Financials', 'Consolidated Statement of Comprehensive Income', '141'),
        (46, 'Financials', 'Consolidated Statement of Financial Position', '142'),
        (47, 'Financials', 'Consolidated Statement of Changes in Equity', '143'),
        (48, 'Financials', 'Consolidated Statement of Cash Flows', '144'),
        (49, 'Financials', 'Notes to the Consolidated Financial Statements', '145'),
        (53, 'Others', 'Shareholder Information', '231'),
        (54, 'Others', 'Glossary', '234'),
    ],
}
for _sid, _entries in REVIEW_DIRECTORY_ASSERTIONS.items():
    for _line, _parent, _label, _page in _entries:
        REVIEW_TYPED_ASSERTIONS[(_sid, _line)] = [('', _label, _page, {})]
        REVIEW_REPRESENTATION_POLICIES[(_sid, _line)] = 'either'
REVIEW_CONTROL_ASSERTIONS = {}
REVIEW_ORDERED_SOURCE_GROUPS = {
    'hkex-chairman-statement-p017-020': [(406, 410, 'Carlson Tong, chairman and Hong Kong date attribution')],
    'hkex-strategic-message-p007': [(74, 76, 'Bonnie Y Chan attribution and chief executive officer title')],
    'hkex-independent-auditor-p137-141': [(4389, 4395, 'engagement partner, audit firm, professional title and signed date')],
    'hkex-nomination-governance-p105-108': [(3346, 3350, 'Carlson Tong, NGC chairman and signed Hong Kong date')],
    'pingan-chairman-p014-019': [(560, 564, 'chairman, Shenzhen PRC and March 19 2025 attribution')],
}

SOURCE_REVIEW_NOTES = {
    'hkex-chairman-statement-p017-020': {
        'reviewed': True,
        'scope': 'All four selected pages; repeated opening statement is intentionally retained twice; no image inspection.',
        'responsibilities': ['Cash/Derivatives/ETP and Connect records', 'revenue/profit and cash-dividend distinctions',
            'conditional 2025 LME programme and CBAM deadline', 'carbon neutrality versus submitted SBTi validation',
            'four evaluated boards', '86 million donation and stakeholder acknowledgements', 'chairman signature attribution'],
        'applicability': 'Caption and headings are structure/text responsibilities, not additional B assertions; no layer grade is assigned.',
        'additional_counting_gap': {'line': 390,
            'expected': 'The single complete Further-details sentence has one membership in Corporate Responsibility, not two copies of that scope vote.',
            'observed': 'Retained prose_heading_membership and whole-source content document_scope both count the same complete sentence and same parent scope.'},
    },
    'hkex-contents-p003': {
        'reviewed': True,
        'scope': 'Complete contents selection, all six groups and 25 printed entries; page numbers are references, not business quantities.',
        'responsibilities': ['entry/page association', 'six selected parent categories', 'original reading order', 'HKD unless otherwise stated'],
        'required_structure': 'Each printed page belongs to its exact entry in its group; intact word/page union alone cannot accept a swapped page reference.',
        'fresh_observation': 'Overview at L13 has neither heading_parent nor content requirement. Eleven retained generic metric fields are page references; the role-sensitive entry/page contract needs independent verification, not quantity equivalence.',
        'review_conclusion': 'returned_for_specific_coverage_gap',
    },
    'hkex-strategic-message-p007': {
        'reviewed': True,
        'scope': 'All six selected sources, including author attribution.',
        'responsibilities': ['2024 achievements versus 2025 outlook', 'third-quarter sentiment and prudent costs',
            '25th listing anniversary', 'Bonnie Y Chan is chief executive officer'],
    },
    'hkex-operational-timeline-p008-009': {
        'reviewed': True,
        'scope': 'Both selected pages; two photo captions and all five dated sections are retained.',
        'responsibilities': ['announcement date versus later effective date', 'duplicate 19 Dec/2 Sep/18 Dec labels retain distinct records',
            '2024 events versus January/June/July 2025 implementation', 'Court of Appeal dismissal versus Supreme Court permission refusal',
            'Connect collateral and bond types', 'carbon neutrality and emissions-target submission'],
        'date_role': 'Timeline labels are printed calendar labels; no conversion to amount or invented year on individual date labels.',
        'oracle_correction': 'Initial default-content assumption rejected correctly printed short label/value fields; the independent source declarations now explicitly permit both complete source representations for every dated record, not only current production hits.',
    },
    'hkex-independent-auditor-p137-141': {
        'reviewed': True,
        'scope': 'All five selected pages, both key-audit-matter subtrees and every audit-procedure item.',
        'responsibilities': ['six financial-statement components', 'HKFRSs/HKICPA/Companies Ordinance opinion',
            '13,297 total versus 13,192 LME goodwill', 'Commodities CGU and five-year cash-flow assumptions',
            'no separate KAM opinion', 'IT control categories', 'other-information exclusion',
            'directors versus auditor responsibilities', 'reasonable assurance is no guarantee',
            'fraud-risk distinction and going-concern conditions', 'Section 405 addressee restriction',
            'Peter Po-ting Li/PricewaterhouseCoopers signing attribution'],
        'additional_counting_gap': {'line': 4350,
            'expected': 'The single complete IT-control-reliance conclusion has one membership in its audit-procedures heading scope.',
            'observed': 'Retained prose_heading_membership and whole-source content document_scope both count the same complete source and same four-level parent scope.'},
    },
    'hkex-nomination-governance-p105-108': {
        'reviewed': True,
        'scope': 'All four selected pages and the complete governance/independence list hierarchy.',
        'responsibilities': ['five INEDs/four meetings', 'appointment, resignation and term endpoints',
            '31 per cent and at least four women', 'nine consecutive years nomination limit',
            'Brien/Yam/Chinachem/Trustee role distinction', 'except statutory compensation',
            'Rule 3.13 independence and own-assessment abstention', '12 INEDs versus sole executive director',
            'fixed fees and no Share Award Scheme', 'company-paid advice and director commitment', 'NGC chairman attribution'],
        'oracle_correction': 'L3303 is an existing complete supported affirmative copula assertion; its exact subject, predicate, object, present tense and polarity are now required rather than the initial default-content assumption.',
    },
    'pingan-chairman-p014-019': {
        'reviewed': True,
        'scope': 'All eight declared selections covering six pages; all prose, photographs/illustration/signature captions and printed descriptions.',
        'responsibilities': ['operating/net profit and revenue distinguish metrics and YoY',
            'proposed final versus full-year cash dividend and payout ratio', 'retail customers/contracts/retention/channel figures',
            'Life & Health and P&C and Bank boundaries', 'health/senior-care income/users/benefits',
            'AI scenario/volume/efficiency/accuracy dimensions', 'green investments/loans/premiums/rural funding',
            '2024 achievements versus 2025 policies', 'chairman location and signed date'],
        'images': 'Only authorized alt text and adjacent descriptions; no claim about unseen image content.',
    },
    'pingan-integrated-finance-p022-024': {
        'reviewed': True,
        'scope': 'All three selections; initial H4 headings are selected roots and do not import the unselected Integrated Finance parent as an answer.',
        'responsibilities': ['63% benefit group and respective 1.6/3.8 multipliers', 'three growth drivers and benign pressure qualifiers',
            'operating-profit note/4.0% assumption/rounding', 'tenure and product retention comparisons',
            'outlet/city/sales-member versus app-user fields', 'product-specific penetration and paired changes', 'chart caption hierarchy'],
        'identifiers': 'App names retain quoted literal identity; +/~ and thousand/mn scales are not discarded.',
        'fresh_observation': 'L668 may-not-match rounding note is retained as subject `(3) Figures`, predicate `match`, object `match the calculation due to rounding`. The duplicated predicate and numbered-note actor do not independently establish the complete printed rounding disclaimer responsibility.',
        'review_conclusion': 'returned_for_specific_coverage_gap',
    },
    'pingan-mission-opportunities-p006-007': {
        'reviewed': True,
        'scope': 'Both pages, separate repeated WHY WE’RE HERE under distinct top-level sections, all projections and source notes.',
        'responsibilities': ['three service promises', '24/7 and 3-in-1 member roles', 'expected 2030/2035 horizons',
            'one-third versus RMB16/RMB30 trillion forecasts', 'over 20%, aged 65+, 10% GDP',
            '9073 allocation with home/community/institutions', 'three distinct numbered forecast-source notes', 'photograph captions only'],
    },
}

# The requirements retain these sources, but their numeric token roles still
# need independent comparison evidence. Literal source-graph assertions alone
# cannot certify the comparison of a day, reporting year or page identifier.
REVIEW_NUMERIC_ROLE_DEPENDENCIES = {
    'hkex-chairman-statement-p017-020': [
        {'line': 410, 'role': 'signed_calendar_date', 'case_id': 'numeric-role/calendar-attribution'}],
    'hkex-contents-p003': [
        {'line': 16, 'role': 'page_reference', 'case_id': 'numeric-role/page-reference'}],
    'hkex-strategic-message-p007': [
        {'line': 70, 'role': 'reporting_or_outlook_year', 'case_id': 'numeric-role/reporting-year'}],
    'hkex-operational-timeline-p008-009': [
        {'line': 84, 'role': 'calendar_event_label', 'case_id': 'numeric-role/calendar-label'},
        {'line': 84, 'role': 'calendar_label_in_scalar_identity', 'case_id': 'numeric-role/typed-calendar-label'},
        {'line': 91, 'role': 'effective_calendar_date', 'case_id': 'numeric-role/calendar-body'}],
    'hkex-independent-auditor-p137-141': [
        {'line': 4395, 'role': 'signed_calendar_date', 'case_id': 'numeric-role/calendar-attribution'}],
    'hkex-nomination-governance-p105-108': [
        {'line': 3350, 'role': 'signed_calendar_date', 'case_id': 'numeric-role/calendar-attribution'}],
    'pingan-chairman-p014-019': [
        {'line': 564, 'role': 'signed_calendar_date', 'case_id': 'numeric-role/calendar-body'}],
    'pingan-integrated-finance-p022-024': [
        {'line': 642, 'role': 'as_of_calendar_date', 'case_id': 'numeric-role/calendar-body'}],
    'pingan-mission-opportunities-p006-007': [
        {'line': 251, 'role': 'forecast_horizon_year', 'case_id': 'numeric-role/reporting-year'}],
}
