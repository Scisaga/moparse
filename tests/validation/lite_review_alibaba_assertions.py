"""Handwritten complete-selection assertions for the fixed 23-source batch.

Read from the authorized expected text before inspecting compiled projections.
English and Chinese passages are separate printed responsibilities: no inferred
translation, entity resolution, image interpretation or external-page context.
"""

REVIEW_ASSERTIONS = {
    'alibaba-mission-values-p003': ('complex-alibaba-2025-annual', [3], [(29, 50)], '''
29|H2|Our Mission, Our Vision and Our Values
31|H3|OUR MISSION
33|P|Our mission is to make it easy to do business anywhere.
35|P|champion small businesses~Internet would level the playing field~domestic and global economies~customer needs~consumers, merchants or enterprises~digital technology, AI and cloud infrastructure~over the long term, not by the pursuit of short-term gains
37|H3|OUR VISION
39|P|We do not pursue size or power~last for 102 years~founded in 1999~spanned three centuries~culture, business models and systems~sustainability in the long run
41|H3|OUR VALUES
43|P|fundamental to the way we operate~recruit, evaluate and compensate our people
45|I|Customers first, employees second, shareholders third~in order of priority~Only by creating sustained customer value~employees grow~shareholders achieve long-term benefit
46|I|Trust makes everything simple~most precious and fragile~building and cherishing trust~Aliren (阿里人)~no second-guessing or suspicion~simplicity and efficiency
47|I|Change is the only constant~world is changing~customers are changing~competitive landscape is changing~respect and humility~fail to catch up~change yourself or create change~most unique part of our DNA
48|I|Today’s best performance is tomorrow’s baseline~most challenging times~overcome difficulties and survive~bad times~good times~“dream targets” (stretch goals)~Face the future, or we regress~exceed ourselves
49|I|If not now, when? If not me, who?~first job advertisement~first proverb~not a question, but a call of duty~sense of ownership~each Aliren
50|I|Live seriously, work happily~Work is now, life is forever~responsibility to the ones who love you~Enjoy work~treat life seriously~live with purpose~respect each person’s choice~how you live your life
'''),
    'alibaba-company-overview-p006-008': ('complex-alibaba-2025-annual', [6, 7, 8],
        [(110, 138), (140, 164), (166, 166), (168, 178)], '''
110|H2|Business Overview
112|H3|Company Overview
114|P|“user first, AI-driven”~two core businesses of e-commerce and cloud~technology infrastructure and marketing reach~cloud and AI infrastructure and services~digital transformation~AI technology will also enhance user value
116|P|In fiscal year 2025~Taobao and Tmall Group~Alibaba International Digital Commerce Group~Cloud Intelligence Group~Cainiao Smart Logistics Network Limited~Local Services Group~Hujing Digital Media and Entertainment Group~All others~consumers, merchants, brands, retailers, enterprises~strategic alliance partners
118|P|in fiscal year 2026~Taobao and Tmall Group, Ele.me and Fliggy will be merged into China e-commerce business group~comprehensive consumption platform~Cainiao, Amap and Hujing Digital Media and Entertainment Group will be reclassified to All others
120|H4|Taobao and Tmall Group
122|H5|China Commerce Retail
124|P|largest retail commerce business in the world~in terms of GMV~twelve months ended March 31, 2025~according to Analysys~primarily consisting of Taobao and Tmall~daily lives of consumers in China
126|P|product and supply chain capabilities~fulfillment and delivery expertise~quality products and services at attractive prices~wide selection of delivery options
128|H5|China Commerce Wholesale
130|P|1688.com~China’s largest integrated domestic wholesale marketplace~twelve months ended March 31, 2025~by net revenue according to Analysys~wholesale buyers and sellers
132|H4|Alibaba International Digital Commerce Group
134|P|various retail and wholesale platforms~brands, merchants and SMEs~global buyers and consumers~wide product selection and differentiated customer experiences
136|H5|International Commerce Retail
138|P|AliExpress, Trendyol and Lazada~manufacturers and distributors in China and around the world~AliExpress’ Choice~product selection, price and quality~speed of logistics~Trendyol~Türkiye~GMV in 2024 according to Euromonitor~Gulf region~Lazada~Southeast Asia~local SMEs~logistics services to its consumers and merchants
140|H5|International Commerce Wholesale
142|P|Alibaba.com~China’s largest integrated international online wholesale marketplace~twelve months ended March 31, 2025~by revenue~according to Analysys~During fiscal year 2025~over 190 countries
144|H4|Cloud Intelligence Group
146|P|world’s fourth largest and Asia Pacific’s largest~Infrastructure-as-a-service provider~revenue in 2024 in U.S. dollars~Gartner April 2025 report~11 April 2025~Vendor Revenue Basis~Mature Asia/Pacific, China (Region), Emerging Asia/Pacific and Japan (Region)~China’s largest provider of public cloud services~PaaS and IaaS~IDC~(2024Q4)~computing, storage, network, security, database, big data, container and AI-related~Qwen3~across Alibaba’s ecosystem~Qwen model series on the cloud~individualized models for their business scenarios
148|H4|Cainiao Smart Logistics Network Limited
150|P|smart logistics network~end-to-end logistics capabilities~global scale~controls the key nodes~service quality, efficiency and reliability~trusted partners’ capabilities~scalability and capital efficiency~both our e-commerce businesses as well as third parties
152|H4|Local Services Group
154|P|proprietary mobile and online technology~efficiency, effectiveness and convenience~Ele.me and Amap
156|P|Ele.me~leading local services and on-demand delivery platform in China~Ele.me, Taobao and Alipay apps~meals, food, groceries, FMCG, flowers and pharmaceutical products
158|P|Amap~mobile digital map, navigation and real-time traffic information in China~one-stop access point~navigation, local services and ride-hailing
160|H4|Hujing Digital Media and Entertainment Group
162|P|In May 2025~rebranded to Hujing Digital Media and Entertainment Group~“Content + Technology”~online and offline entertainment~Alibaba Pictures was renamed as Damai Entertainment in June 2025~especially in the offline entertainment market
164|P|consumption opportunities beyond our commerce business~commerce business and our proprietary data technology~superior entertainment experience~customer loyalty~monetization for content providers
166|P|Youku and Damai Entertainment~online long-form video platform in China~applying AI technologies~content production, promotion and distribution~performance and event ticketing management~intellectual property-related licensing~cinema ticketing management and Internet data services~online and offline entertainment channels
168|H4|All others
170|P|new service and product offerings~evolving needs~efficiency~synergies~DingTalk~collaboration workplace and enterprise management platform~Quark~AI-powered information services platform in China~information search, storage, and consumption
172|H4|Our Ecosystem
174|P|consumers, merchants, brands, retailers, enterprises, third-party service providers, strategic alliance partners~technology platform~marketplace rules~discover, engage and transact~greater good of the ecosystem~balancing the interests~ownership~“our ecosystem.”~self-reinforcing network effects
176|P|following chart~main businesses for fiscal year 2025 by segment
178|C|Our Ecosystem
'''),
    'alibaba-shareholder-letter-p004-005': ('complex-alibaba-2025-annual', [4, 5], [(52, 78), (80, 108)], '''
52|H2|Letter from our Chairman and our CEO
54|H3|Dear Shareholders,
56|P|Fiscal year 2025~solid progress~“user first, AI-driven” strategy
58|P|two core businesses~e-commerce and “AI + Cloud”~twin engines~long-term growth~increased investments in cloud computing and AI infrastructure~industrial adoption of AI technologies
60|P|divestiture of non-core assets~Sun Art and Intime~operating efficiency~Hujing Digital Media and Entertainment Group and Amap~each achieved a profitable quarter in fiscal year 2025~group-wide strategy~holistic value creation
62|P|historic opportunities brought by AI~forward-looking perspective~strategic positioning, competitive strengths~next wave of growth
64|H3|Strategic Execution and Business Updates
66|P|first strategic focus, “user first,”~Internet platform businesses
68|P|over 1.1 billion Internet users~world’s largest online retail market~nearly 27% of total retail consumption~Taobao and Tmall Group~user growth and improving user experience~merchants~high-quality products and services~consumers, merchants, and the platform~fiscal year 2025~consumer and merchant trust~business acceleration
70|P|Alibaba International Digital Commerce Group (AIDC)~robust revenue growth~cross-border e-commerce businesses~local supply in key markets~Operating efficiency continued to improve~confident~profitable quarter~coming fiscal year
72|P|second strategic focus, “AI-driven,”~core driver of business growth~transformative force~Over the next decade~expected to reshape every industry~investing aggressively~AI infrastructure and frontier innovation~global competitiveness
74|P|Alibaba Cloud~surging AI demand~Public cloud revenue growth accelerated~AI-related products~triple-digit growth for seven straight quarters~overall revenue to double-digit growth for the fiscal year
76|P|foundation models~open-source development~In April 2025~Qwen3~top models globally~As of the end of April 2025~over 200 models~more than 300 million global downloads~over 100,000 derivative models~world’s largest open-source model family~We believe~global developers~artificial general intelligence (AGI)
78|P|broader Internet platform ecosystem~open and forward-looking mindset~not only a catalyst~but also a key~new user experiences and value
80|H3|Capital Management and Shareholder Return
82|P|In fiscal year 2025~strong cash flow~core businesses~previously loss-making businesses~on track to profitability~disciplined capital allocation~Sun Art and Intime~invest strategically in AI
84|P|distributed US$4 billion~annual and special dividends for fiscal year 2024~announced a total of US$4.6 billion~dividends for fiscal year 2025~repurchased US$11.9 billion~5.1% net reduction in total outstanding shares~earnings per share
86|P|Looking ahead~committed to enhancing shareholder value through multiple avenues
88|H3|Investing for the Future
90|P|rapid evolution of AI~sweeping changes across industries~unprecedented growth opportunities for Alibaba
92|P|Over the next decade~primary driver of incremental value and transformation~world-class AI models~globally competitive AI-enabled cloud infrastructure~“AI + Cloud”~key growth engine
94|P|three key areas: AI and cloud infrastructure, AI foundation models and native applications, and the AI-driven transformation of our existing businesses~In fiscal year 2025~planned investment~over the next three years~will exceed~past decade
96|P|China cloud computing market~top cloud services provider in Asia Pacific~global cloud computing infrastructure~international deployment of AI-related products~globalization of Chinese enterprises~confident~second growth curve
98|P|startup mindset~thinking boldly and acting decisively~Alibaba Day~creation, not preservation~heart of an entrepreneur~ambition to lead
100|P|Joe Tsai
102|P|Chairman
104|P|Eddie Wu
106|P|Chief Executive Officer
108|P|June 26, 2025
'''),
    'alibaba-risk-summary-p105-108': ('complex-alibaba-2025-annual', [105, 106, 107, 108],
        [(2254, 2277), (2278, 2302), (2302, 2321), (2323, 2351)], '''
2254|H1|Risk Factors
2256|H2|Summary of Risk Factors
2258|P|may involve significant risks~Cayman Islands holding company~does not directly engage in business operations~foreign ownership and investment~restricted or prohibited in the PRC~VIEs~owned by PRC citizens~not by our company~contractual arrangements~effective control~substantially all of the economic risks and benefits~U.S. GAAP~ADSs and Shares~rather than equity securities issued by our consolidated subsidiaries and the VIEs~Business Overview — Organizational Structure~Risks Related to Our Corporate Structure
2260|P|legal and operational risks and uncertainties~primarily operating in China~PRC government~oversee and regulate~overseas listing and overseas fundraisings~Risks Related to Doing Business in the People’s Republic of China
2262|P|summary of the risk factors~read this summary together with the detailed risk factors~annual report
2264|P|Risks and uncertainties related to our business and industry~the following
2266|I|maintain the trusted status~maintain and improve the network effects
2267|I|maintain or grow our business~sustained investment~margins and net income
2268|I|compete effectively~continue to innovate~adapt to changes
2269|I|management, operational and financial challenges~maintaining and growing our business and operations~maintain our culture
2270|I|economic conditions~geopolitical tensions~natural disasters or widespread health epidemics
2271|I|national trade or investment policies~barriers~geopolitical conflicts~export control~sanctions~“de-coupling” and “de-risking”
2272|I|reputational harm, liabilities~business dealings~merchants or consumers~sanctioned countries or persons
2273|I|expanding our international and cross-border businesses and operations
2274|I|acquisitions, investments and alliances~regulatory approval and review requirements
2275|I|evolving laws and regulations~including but not limited to~digital platforms~privacy, data protection and cybersecurity~competition laws~content regulations~consumer protection laws
2276|I|security breaches and cyber-attacks
2277|I|pirated, counterfeit or illegal~content~infringements of intellectual property rights~protect our intellectual property rights
2278|I|material litigation and regulatory proceedings
2279|I|maintain or improve our technology infrastructure~performance, reliability and security~network and system interruptions
2280|I|Ant Group and Alipay~reliance on Alipay~payment processing and escrow services~significant majority~commerce business~conflicts of interests
2281|I|wide range and large number of third-party service providers and ecosystem participants
2282|I|attract, motivate and retain~key management~experienced and capable personnel
2283|I|fraudulent or illegal activities~employees, business partners and service providers~fraud~fictitious transactions
2284|I|tax compliance efforts~merchants
2285|I|public scrutiny~aggressive marketing and communication strategies~competitors
2286|I|quarter-to-quarter fluctuations~results of operations
2287|I|comply with~terms of our indebtedness~obligations as a guarantor~raise additional capital~interest rate risks~and
2288|I|potential insufficiency of insurance coverage
2290|P|Risks and uncertainties related to our corporate structure~following
2292|I|shareholders’ limited ability~nominate and elect directors
2293|I|differences between the interests~Alibaba Partnership~shareholders
2294|I|anti-takeover provisions~Articles of Association~convertible senior notes~discouraging acquisitions
2295|I|shareholders do not hold equity securities~subsidiaries and the VIEs~substantive business operations in China~and
2296|I|VIE structure~regulatory risks~limitations of contractual arrangements~control~potential failure~perform their obligations~licenses, approvals and assets~conflicts of interests~equity holders, directors and executive officers~PRC tax authority
2298|P|Risks and uncertainties related to doing business in the PRC~following
2300|I|political and economic policies~intervene in or influence our operations~evolve quickly with little advance notice~interpretation and enforcement~page 145 through 146
2301|I|interpretation and enforcement~oversight and control~offerings that are conducted overseas~foreign investment in China-based issuers~limit or completely hinder~offer securities~decline in value or become worthless~page 145 through 146
2302|I|PCAOB’s ability to inspect our auditors~potential delisting of our ADSs~HFCA Act~historically been unable~future may deprive our investors~Holding Foreign Companies Accountable Act, as amended~unable to inspect or investigate completely~page 146 and page 147
2303|I|investments in offshore companies~employee equity incentive plans~PRC-resident beneficial owners~liability or penalties~inject capital~registered capital or distribute profits~fines and other legal or administrative sanctions~page 148 and page 148
2304|I|dividends, loans and other distributions~operating subsidiaries in China~restrictions and limitations~transfer cash or assets~fund operations~outside of the PRC~fluctuations in exchange rates~page 149
2305|I|PRC income tax on our global income~potential discontinuation~preferential tax treatments~resident enterprise~PRC Enterprise Income Tax Law~page 149
2306|I|dividends payable to foreign investors~gains on the sale~PRC taxation~indirect transfers of equity interests~PRC establishment of a non-PRC company~page 149~and
2307|I|approval, filing or other requirements~future issuance of securities overseas~CSRC~if required~cannot predict whether or for how long~page 151 through 152
2309|P|Risks related to our ADSs and Shares~following
2311|I|volatilities in the trading prices~future sales~active trading markets~conversion of our convertible senior notes~capped call transactions
2312|I|changes to our shareholder return initiatives
2313|I|Hong Kong and the U.S.~public offering and listing~Shanghai or Shenzhen
2314|I|limited ability~shareholders and U.S. authorities~bring actions against us
2315|I|exemptions~NYSE corporate governance standards~disclosure requirements~different practices~listed in Hong Kong
2316|I|limitations~ADS holders~vote, transfer ADSs and receive distributions~ordinary shares~discretionary proxy~depositary
2317|I|exchange between our Shares and our ADSs~liquidity and/or trading prices~delays
2318|I|may be or may become a passive foreign investment company~and
2319|I|uncertainty~Hong Kong stamp duty~trading or conversion of our ADSs
2321|P|various risks and uncertainties~in detail below
2323|H2|Risks Related to Our Business and Industry
2325|H3|Maintaining the trusted status of our ecosystem is critical to our success and growth, and any failure to do so could severely damage our reputation and brand, which would have a material adverse effect on our business, financial condition, results of operations and prospects.
2327|P|strong brand name and reputation~loss of trust~reducing their levels of activity~materially reduce our revenue and profitability~ability to maintain trust~based in large part upon
2329|I|developing and leveraging cutting-edge technology~including AI~consumers, users and customers
2331|I|attract and retain consumers~superior user experience~quality, safety, value and functionality~products, services and content
2333|I|deliver value to brands, merchants and enterprises~thrive on our platforms
2335|I|reliability, stability and integrity~company, platforms, systems and services~merchants, software developers, logistics providers, service providers
2337|I|safety, security and integrity~data on our systems~other participants
2339|I|collect, process, store and utilize user data~changes in the related regulations and user expectations
2341|I|effectiveness and fairness~rules governing our marketplaces~overall ecosystem
2343|I|strength of our measures~protect consumers and intellectual property rights owners~and
2345|I|reliable and trusted services~payment and escrow services~Alipay or other partners
2347|P|businesses operate more independently~failure by any of our businesses~own trusted brand~harm~brand name and reputation
2349|H3|We may not be able to maintain or grow our business.
2351|P|future depends on a number of factors~number and engagement of consumers~value~data and technology capabilities~attract and retain cloud infrastructure customers~Management Discussion and Analysis — Operating Results — Factors Affecting Our Results of Operations — Our Ability to Create Value for Our Users and Generate Revenue.~competition~not be within our control~macroeconomic environment, inflation, deflation~pandemics, natural disasters, armed conflicts~geopolitical landscape and government policies~may not continue to grow as quickly or at all
'''),
    'tencent-enforcement-notices-jurisdiction-p149-151': ('complex-tencent-2025-bond-programme', [149, 150, 151],
        [(2082, 2100), (2102, 2118), (2119, 2122)], '''
2082|I|(d) Certificates and Reports:~Trustee may rely without liability to Noteholders~whether or not addressed to it~whether their liability~limited~monetary cap, methodology or otherwise~binding on the Issuer, the Trustee and the Noteholders
2084|H2|20. Enforcement
2086|P|at its absolute discretion and without notice~enforce its rights under the Trust Deed~not be bound to do so unless:
2088|I|(i)~requested in writing~Holders of at least one quarter~aggregate principal amount~outstanding Notes~or~Extraordinary Resolution~and
2089|I|(ii)~indemnified and/or pre-funded and/or provided with security~to its satisfaction
2091|P|No Noteholder may proceed directly~unless the Trustee~having become bound~fails~reasonable time~failure is continuing
2093|H2|21. Further Issues
2095|P|without the consent of the Noteholders or the Couponholders~same terms and conditions~except for the first payment of interest~single series~provided that~Registered Notes~same CUSIP, ISIN or other identifying code~fungible~U.S. federal income tax purposes~provided further~Bearer Notes~“TEFRA D”~Temporary Global Note~Permanent Global Note~only following certification of non-U.S. beneficial ownership~in accordance with the TEFRA D Rules
2097|H2|22. Notices
2099|I|(a) Bearer Notes:~valid if published~English language daily newspaper~Hong Kong~not practicable~general circulation in Asia~date of first publication~more than one newspaper~first date~all the required newspapers~Couponholders~notice of the contents
2100|I|(b) Registered Notes:~first class mail~equivalent~overseas address~airmail~addresses on the Register~fourth day after the date of mailing
2102|P|So long as~Global Note or a Global Note Certificate~(i) Euroclear or Clearstream, DTC~except as provided in (ii)~delivery~clearing system~in substitution for publication~(ii) the CMU Service~Persons shown in a CMU Instrument Position Report~Hong Kong Monetary Authority~business day preceding the date of despatch
2104|H2|23. Currency Indemnity
2106|P|If any sum due~Notes or the Coupons~order or judgment~“first currency”~“second currency”~(a) making or filing a claim or proof~(b) obtaining an order or judgment~(c) enforcing any order or judgment~Issuer shall indemnify each Noteholder~written demand~Specified Office of the Principal Paying Agent~any discrepancy~(i) the rate of exchange used~(ii) the rate or rates of exchange~in whole or in part
2108|P|separate and independent obligation~Issuer~separate and independent cause of action
2110|H2|24. Rounding
2112|P|unless otherwise specified~relevant Pricing Supplement~(a) all percentages~nearest one hundred-thousandth of a percentage point~0.000005 per cent.~rounded up to 0.00001 per cent.~(b) all United States dollar amounts~nearest cent~one half cent~rounded up~(c) all Japanese Yen amounts~rounded downwards~next lower whole Japanese Yen amount~(d)~any other currency~nearest two decimal places~0.005 being rounded upwards
2114|H2|25. Governing Law and Jurisdiction
2116|I|(a) Governing law:~Notes, the Trust Deed~non-contractual obligations~English law
2117|I|(b) English courts:~courts of England~“Dispute”~existence, validity or termination~non-contractual obligation~nullity
2118|I|(c) Appropriate forum:~courts of England~most appropriate and convenient~will not argue to the contrary
2119|I|(d) Rights of the Noteholders to take proceedings outside England:~Condition 25(b)~benefit of the Noteholders only~nothing in this Condition 25 prevents~other courts with jurisdiction~To the extent allowed by law~concurrent Proceedings~any number of jurisdictions
2120|I|(e) Process agent:~Cogency Global (UK) Limited~6 Lloyds Avenue, Unit 4CL, London EC3N 3AX, United Kingdom~not or ceases to be effectively appointed~written demand~further person in England~failing such appointment within 15 days~any Noteholder~Nothing in this paragraph~any other manner permitted by law~Proceedings in England and to Proceedings elsewhere
2121|I|(f) Consent to enforcement etc.:~Issuer consents generally~giving of any relief~issue of any process~without limitation~any property whatsoever~irrespective of its use or intended use~order or judgment
2122|I|(g) Waiver of immunity:~To the extent~any jurisdiction~itself or its assets or revenues~suit, execution, attachment~before judgment or otherwise~agrees not to claim and irrevocably waives~full extent permitted~laws of such jurisdiction
'''),
    'byd-bilingual-review-p013-024': ('complex-byd-2024-annual', list(range(13, 25)),
        [(299, 321), (323, 341), (343, 369), (371, 371), (373, 387),
         (389, 389), (391, 391), (393, 393), (395, 395), (397, 407),
         (409, 419), (421, 427), (429, 435)], '''
299|P|“technology-based, innovation-oriented”~31 December 2024~average of 45 patent applications and 20 patent licensing on each working day~“Integrated Vehicle Intelligence”~“God’s Eye (天神之眼)”~mapless city navigation function nationwide~In May~“Fifth-generation DM Technology”~highest engine thermal efficiency of 46.06% available for mass production~lowest fuel consumption at low battery charge level of 2.9L per 100km~longest mileage of 2,100km~new era of “2”
301|P|multi-brand strategy~“BYD”, “FANGCHENGBAO”, “Denza” and “Yangwang”~sales volume~new highs repeatedly during the Year
303|P|“BYD”~mass market~“NEV cheaper than ICE”~“e-Platform 3.0 Evo”~“Fifth-generation DM Technology”~new product cycle~new models
305|P|“FANGCHENGBAO”~brand renewal strategy~“start with off-road, more than off-road”~personalized driving needs~“BAO 5”~five months in a row~“BAO 8”~top three~RMB400,000-level new energy SUV segment
307|P|“Denza”~world’s first~full category of MPVs, SUVs and sedans~“Denza D9”~top position in annual sales across the entire MPV market for two years~“Denza Z9GT”~starting price of RMB300,000~three months in a row
309|P|“Yangwang”~million-level market segment~cutting-edge technology~“Yangwang U8”~hardcore off-road~“Yangwang U9”~battery electric performance supercar~“Yangwang U7”~new energy flagship sedan
311|P|技術為王、創新為本~二零二四年十二月三十一日~平均每個工作日專利申請45項、專利授權20項~整車智能~天神之眼~全國範圍內~無圖城市領航~五月~第五代DM技術~全球量產最高發動機熱效率46.06%~全球最低百公里虧電油耗2.9L~全球最長綜合續航2,100公里~油耗「2」時代
313|P|多品牌策略~比亞迪~方程豹~騰勢~仰望~年內各品牌攜手並進~銷量屢破前高
315|P|比亞迪~大眾化市場~產品矩陣持續優化迭代~電比油低~e平台3.0 Evo~第五代DM技術~全新產品週期~全新車型
317|P|方程豹~新能源個性化品牌~整體的品牌煥新戰略~始於越野 不止越野~更多元、更廣泛用戶人群~豹5~連續五個月~新能源硬派越野銷量冠軍~豹8~40萬級新能源SUV月度銷量前三
319|P|騰勢~全球首個覆蓋MPV、SUV和轎車全品類~騰勢D9~連續兩年~MPV全市場年銷量第一~騰勢Z9GT~連續三個月~30萬起售新能源豪華轎車市場第一
321|P|百萬級~仰望~不同場景需求~仰望U8~新能源硬派越野~仰望U9~純電性能超跑~仰望U7~新能源旗艦轎車
323|P|passenger vehicle business~top tier global dealers~Uzbekistan and Thailand~put into production successively~“EXPLORER NO.1” and “BYD CHANGZHOU”~By the end of 2024~more than 100 countries and regions~six continents
325|H4|2.2 Handset Components and Assembly Business
327|P|technical strength~manufacturing capability~new products for customers~new intelligent product business~3D printers and AI servers realising mass production~liquid cooling and power supply products~completed during the Year
329|H4|2.3 Shareholder Returns and Corporate Social Responsibility
331|P|repurchased its A shares~self-owned funds for the first time~cancellation~in May~in November~2024 Employee Share Ownership Plan~corporate value~shareholders~employees~In 2024~domestic tax~approximately RMB51,024 million~charitable activities~education, poverty relief, and environmental conservation~plans to donate a total of RMB3 billion~university scholarships~new energy technologies
333|P|乘用車業務全球化佈局~海外銷量~全球優質經銷商~烏茲別克斯坦和泰國工廠陸續投產~EXPLORER NO.1~BYD CHANGZHOU~截至二零二四年底~全球6大洲、100多個國家和地區
335|H4|2.2 手機部件及組裝業務
337|P|技術優勢~製造能力~新產品開發~新型智能產品業務~3D打印機、AI服務器於年內實現量產~液冷和電源產品完成開發
339|H4|2.3 股東回報及企業社會責任
341|P|首次使用自有資金回購A股股票~五月成功完成註銷~十一月~二零二四年員工持股計劃~企業價值~股東~員工~二零二四年~國內納稅總額約為51,024百萬元~助學、扶貧、環保~計劃捐資總計30億元~高校獎學金及新能源技術科普
343|H3|3. FUTURE PROSPECT
345|P|In 2025~independency and controllability~core technologies~competitiveness~multi-brand matrix~overseas expansion~China’s automobile industry~global transformation of new energy vehicles
347|P|first automaker globally~rolling out 10 million new energy vehicles~three decades~precise strategy~core technology~swift decision-making and efficient execution~no longer playing catch-up~Chinese brands~“expand globally and rise to new heights”
349|P|handset components and assembly business~core technology R&D and high-end manufacturing innovation~vertical integration advantages~key customers~AI data center, AI servers~expected to progress rapidly
351|P|thirty years~century of possibilities~On behalf of the Group~customers~business partners, investors, and shareholders~every employee~innovate, embrace change~sustainable growth~value to our shareholders
353|P|Wang Chuan-fu~Chairman~Shenzhen, the PRC, 24 March 2025
357|H3|3. 未來展望
359|P|二零二五年~百年變局~核心技術的自主可控~產品競爭力~多品牌矩陣~業務出海~中國汽車產業~全球新能源汽車變革
361|P|全球首家~第1,000萬輛新能源汽車下線~三十年~精準的戰略~核心的技術~快速的決策和高效的執行~不再是跟隨者~敢為天下先~走出去，走上去
363|P|手機部件及組裝業務~核心技術研發及高端製造創新~垂直整合~大客戶戰略合作~AI數據中心、AI服務器~有望快速推進~新的成長曲線
365|P|三十而立，百年為序~本人謹代表本集團~客戶~業務夥伴、投資者及股東~全體員工~長期可持續發展~股東創造最大回報
367|P|主席~王傳福~中國深圳，二零二五年三月二十四日
371|C|汽車照片
373|H2|Management Discussion and Analysis
375|H2|管理層討論與分析
377|H3|1. INDUSTRY ANALYSIS AND REVIEW
379|H4|1.1 Automobiles and Batteries Business
381|P|In 2024~slow recovery~geopolitical conflicts~protectionism~monetary policies~emerging markets in Asia~National Bureau of Statistics~China’s GDP~year-on-year increase of 5.0% in 2024~lack of effective domestic demand~old momentum to the new momentum~real estate and local debts
383|H3|1. 行業分析及回顧
385|H4|1.1 汽車及電池業務
387|P|二零二四年~全球經濟~地緣政治衝突~保護主義~貨幣政策~亞洲新興市場~國家統計局~國內生產總值~同比增長5.0%~有效需求不足~新舊動能轉換~房地產和地方債務風險
389|P|In 2024~high inventory, weak consumption~“two new” national policies~China Association of Automobile Manufacturers~31.282 million units and 31.436 million units~3.7% and 4.5% respectively~sixteenth consecutive year~10 million units~12.888 million units and 12.866 million units~34.4% and 35.5% respectively~tenth consecutive year~China Passenger Car Association~47.6%~12 percentage points~exceeded 50%~five consecutive months~65.2%~9.2 percentage points~5.859 million units~19.3%~world’s largest automobile exporter~1.284 million units~6.7%~sustainable mobility
391|P|二零二四年~庫存高、消費弱~兩新~中國汽車工業協會~3,128.2萬輛和3,143.6萬輛~3.7%及4.5%~連續十六年~年度1,000萬里程碑~1,288.8萬輛和1,286.6萬輛~34.4%和35.5%~連續十年~中國汽車流通協會乘聯分會~47.6%~12個百分點~連續5個月~50%~65.2%~9.2個百分點~585.9萬輛~19.3%~全球汽車出口第一大國~128.4萬輛~6.7%~全球汽車產業的轉型
393|P|In 2024~In March~Action Plan for the Promotion of the Large Scale Equipment Renewal and Trade-in of Consumer Goods~In April, seven ministries~Implementation Rules on Subsidies for Trade-in of Automobiles~scope and standards~application, approval and granting procedures~In May, five ministries~rural areas for 2024~In the same month~2024-2025~lift the restrictions~In July~around RMB300 billion~In August, seven ministries~subsidy standard~central government~Vehicle-Road-Cloud Integrated System~L3 level (conditional self-driving)~on-road traffic and mass production~smart city infrastructure
395|P|二零二四年~三月~推動大規模設備更新和消費品以舊換新行動方案~四月~七部門~汽車以舊換新補貼實施細則~範圍和標準~申報、審核和發放~五月~五部門~新能源汽車下鄉~同月~2024–2025年節能降碳行動方案~逐步取消~七月~3,000億元左右~超長期特別國債~八月~七部門~汽車報廢更新補貼標準~中央資金~車路雲一體化~L3級別（有條件自動駕駛）~上路通行和量產落地~智慧城市基礎設施
397|P|rechargeable batteries~smartphone replacement cycle in 2024~consumer electronics~upstream batteries~energy storage~renewable energy technologies~favorable policies~energy structure transformation~photovoltaic industry~despite the continuous growth~supply and demand conflicts~trade protection~downward trend in the price~challenges in the profitability
399|H4|1.2 Handset Components and Assembly Business
401|P|In 2024~AI technology~handset replacements~IDC~6.4% to 1,240 million units~5.6% year-on-year to 286 million units~after two years of decline~PC shipments~1.0% to 263 million units~Canalys~148 million units~9.2%~AI, 5G communications and the Internet of Things~large model training and inference~AI servers, thermal management, power management~TrendForce~estimated~US$205 billion~67% of the overall server market
403|P|二次充電電池~二零二四年~智能手機換機週期~消費類電子~上游電池需求~儲能~全球多國~利好政策~能源結構轉型~可再生能源~光伏~供需矛盾~海外市場貿易保護~終端產品價格呈下行趨勢~產業鏈各環節盈利面臨一定挑戰
405|H4|1.2 手機部件及組裝業務
407|P|二零二四年~人工智能~換機需求~IDC~上升6.4%至12.4億部~兩年的下跌~同比增長5.6%至2.86億部~PC市場~上升1.0%至2.63億部~Canalys~約1.48億部~同比上升9.2%~AI、5G通信和物聯網~AI數據中心~大模型訓練和推理~AI服務器、熱管理、電源管理~TrendForce~預估~2,050億美元~67%
409|H3|2. BUSINESS REVIEW
411|P|BYD Company Limited~subsidiaries~“the Group”~new energy vehicles~handset components and assembly business~rechargeable batteries and photovoltaic~urban rail transportation~In 2024~approximately RMB777,102 million~29.02%~automobiles and related products, and other products~RMB617,382 million~27.70%~handset components, assembly service and other products~RMB159,609 million~34.60%~79.45% and 20.54%~respectively
413|P|approximately RMB54.2 billion in R&D in 2024~35.68%~cumulative R&D investment~exceeded RMB180 billion~“Dare to Think, Dare to Act, Dare to Persevere”~over 120,000 R&D engineers~batteries, electronics to new energy vehicles~foreign brands~original and disruptive technologies~global green industry~social problems~well-respected world-class brand
415|H3|2. 業務回顧
417|P|比亞迪股份有限公司~本公司~附屬公司~本集團~新能源汽車~手機部件及組裝~二次充電電池及光伏~城市軌道交通~二零二四年~收入約人民幣777,102百萬元~同比增長29.02%~汽車、汽車相關產品及其他產品業務~617,382百萬元~27.70%~手機部件、組裝及其他產品業務~159,609百萬元~34.60%~79.45%和20.54%
419|P|二零二四年研發投入約為542億元~同比上升35.68%~累計研發投入超1,800億元~敢想、敢幹、敢堅持~超12萬名研發工程師~電池、電子到新能源汽車~打破國外品牌統治地位~原創性、顛覆性的技術和產品~全球綠色可持續發展~解決社會問題~世界級品牌
421|H4|2.1 Automobiles and Batteries Business
423|P|global new energy vehicle industry~strategic layout~technical strength~market insights~industrial system~mass market~brand power~global expansion~10 million new energy vehicles in November~China Association of Automobile Manufacturers~In 2024~year-on-year growth of over 40%~33.2%~1.3 percentage points~sales championship among automotive enterprises in China’s automotive market~top-selling brand in China’s automotive market~top seller in the global new energy vehicle market
425|H4|2.1 汽車及電池業務
427|P|全球新能源汽車行業~戰略佈局~技術實力~市場洞察~產業體系~大眾化市場~品牌高端化~汽車業務出海~十一月達成第1,000萬輛新能源汽車下線~中汽協~二零二四年~同比增長超40%~33.2%~1.3個百分點~中國汽車市場車企銷量冠軍~中國汽車市場品牌銷量冠軍~全球新能源汽車市場銷量冠軍
429|H5|Committed to independent innovation to boost new quality productive forces with disruptive and original technologies
431|P|“e-Platform 3.0 Evo”~intelligent fast charging, vehicle safety and vehicle motion control~“Fifth-generation DM Technology”~46.06% available for mass production~2.9L per 100km~2,100km~new era of “2”~“e³ Platform (易三方)”~“Denza”~4.62 meters~65% improvement in parking efficiency~15-degree crab motion
433|H5|堅持自主創新，用顛覆性、原創性技術催生壯大新質生產力
435|P|e平台3.0 Evo~智能快充、整車安全和整車運動控制~第五代DM技術~全球量產最高發動機熱效率46.06%~全球最低百公里虧電油耗2.9L~全球最長綜合續航2,100公里~油耗「2」~騰勢~易三方~4.62米極致轉彎半徑~65%的泊車效率提升~15°蟹行角度
'''),
}

# All long narrative passages retain literal assertions with scope and order;
# identified codes, section numbers, dates and quoted amounts keep their
# printed roles. No blanket numeric equivalence is authorized by this Oracle.
REVIEW_TYPED_ASSERTIONS = {}
REVIEW_REPRESENTATION_POLICIES = {}
REVIEW_CONTROL_ASSERTIONS = {}
REVIEW_SOURCE_OVERRIDES = {
    ('byd-bilingual-review-p013-024', 353): {
        'source_lines': [353, 355],
        'physical_lines': {353: 'Wang Chuan-fu\\', 354: '*Chairman*\\',
                           355: 'Shenzhen, the PRC, 24 March 2025'},
    },
    ('byd-bilingual-review-p013-024', 367): {
        'source_lines': [367, 369],
        'physical_lines': {367: '主席\\', 368: '王傳福\\',
                           369: '中國深圳，二零二五年三月二十四日'},
    },
}
REVIEW_NUMERIC_ROLE_DEPENDENCIES = {
    'alibaba-mission-values-p003': [
        {'line': 39, 'role': 'calendar_foundation_year', 'case_id': 'numeric-role/reporting-year'}],
    'alibaba-company-overview-p006-008': [
        {'line': 118, 'role': 'future_reorganization_fiscal_year', 'case_id': 'numeric-role/reporting-year'}],
    'alibaba-shareholder-letter-p004-005': [
        {'line': 108, 'role': 'signed_calendar_date', 'case_id': 'numeric-role/calendar-attribution'}],
    'alibaba-risk-summary-p105-108': [
        {'line': 2300, 'role': 'printed_legal_page_reference', 'case_id': 'numeric-role/page-reference'}],
    'tencent-enforcement-notices-jurisdiction-p149-151': [
        {'line': 2119, 'role': 'condition_reference_identifier', 'case_id': 'numeric-role/statute-reference'}],
    'byd-bilingual-review-p013-024': [
        {'line': 353, 'role': 'signed_calendar_date', 'case_id': 'numeric-role/calendar-attribution'}],
}
REVIEW_ORDERED_SOURCE_GROUPS = {
    'alibaba-mission-values-p003': [(43, 50, 'Values preamble and six priorities remain in printed order.')],
    'alibaba-shareholder-letter-p004-005': [
        (100, 108, 'Two parallel signatories, their separate titles, and the single dated letter closing.')],
    'alibaba-risk-summary-p105-108': [
        (2264, 2321, 'Four risk preambles with all following sibling bullet lists; no borrowed or dropped risk.'),
        (2327, 2347, 'Trust preamble, nine conditions in their printed order, and the independent-brand consequence.')],
    'tencent-enforcement-notices-jurisdiction-p149-151': [
        (2086, 2091, 'Trustee unless preamble, jointly required (i) and (ii), then the direct-action exception.'),
        (2099, 2102, 'Bearer/registered notice alternatives followed by the global-note substitution conditions.'),
        (2106, 2108, 'Currency conversion indemnity and its independent obligation retain the same legal scope.'),
        (2116, 2122, 'Governing law and all (a) through (g) jurisdiction, process and immunity clauses.')],
}

SOURCE_REVIEW_NOTES = {
    'alibaba-mission-values-p003': {
        'reviewed_sources': 14,
        'basis': 'Complete mission, vision and six value bullets reviewed; 102 years and 1999 remain vision qualifiers, with explicit priority, negation and duty statements.',
        'not_applicable': 'No images, tables or numeric measurement records; headings are structure, not additional business propositions.',
    },
    'alibaba-company-overview-p006-008': {
        'reviewed_sources': 35,
        'basis': 'Complete two-core-business strategy, FY2025 segment membership, future FY2026 merger/reclassification, all sub-businesses, source-qualified market claims, and ecosystem caption reviewed.',
        'not_applicable': 'L178 is only the authorized image caption. No chart content is read or inferred. 1688.com is an identifier, not a quantity.',
    },
    'alibaba-shareholder-letter-p004-005': {
        'reviewed_sources': 29,
        'basis': 'Full letter, actual versus forward-looking claims, 1.1bn/27%, model counts/downloads, each fiscal dividend and repurchase amount, investment horizon, and parallel signatures reviewed.',
        'not_applicable': 'No tables or pictures; date at L108 dates the printed closing, not every prior numerical claim.',
        'coverage_findings': [{
            'line': 56,
            'original': 'Fiscal year 2025 marked a year of solid progress as Alibaba Group advanced our “user first, AI-driven” strategy.',
            'independent_requirement': 'The complete ordered sentence owns the fiscal-year framing and the subordinate Alibaba Group strategy assertion. If typed, Alibaba Group alone is the actor of advanced; the fiscal-year clause cannot be its actor.',
            'observed_defect': 'Retained narrative fact uses Fiscal year 2025 marked a year of solid progress as Alibaba Group as the actor of advance and takes the whole source as a complete typed interpretation.',
            'first_failure_function': 'moparse_eval.narrative_requirements._Reader.clause selects the later recognized advanced predicate, while _Reader.nominal accepts the preceding finite marked/as clause as an actor.',
            'review_status': 'returned_for_incorrect_coverage',
            'required_capability': 'Source guard rejecting an independently finite framing clause inside an actor; preserve the full original sentence with fixed content responsibility rather than a false complete SVO.',
        }],
    },
    'alibaba-risk-summary-p105-108': {
        'reviewed_sources': 70,
        'basis': 'Complete Cayman/VIE ownership and control distinctions; four risk groups; all legal citations, conditional sanctions, trust factors and growth limitations reviewed, including explained sources.',
        'scope_limit': 'Selection ends at L2351; L2353 and its two attachment hypotheses are outside this sample and remain untouched. L2302 is a single source across two selected pages, not duplicate votes.',
        'not_applicable': 'No images or tables. Legal page references and note/section identifiers remain textual citations, not interchangeable numeric measurements.',
    },
    'tencent-enforcement-notices-jurisdiction-p149-151': {
        'reviewed_sources': 25,
        'basis': 'All seven headed clauses plus leading certificate item reviewed: enforcement conjunction, fungibility/TEFRA restrictions, notice alternatives/deeming dates, currency indemnity, currency-specific rounding, jurisdiction rights, process agent and immunity waiver.',
        'scope_limit': 'Leading (d) item has no selected parent. Preserve printed local scope instead of inventing the preceding unselected clause. Rounding thresholds are requirements text, not permission for evaluator rounding.',
        'not_applicable': 'No image/table semantics; alphanumeric postal address, CUSIP/ISIN, clause numbers and monetary/rounding quantities retain distinct roles.',
    },
    'byd-bilingual-review-p013-024': {
        'reviewed_sources': 67,
        'basis': 'All English and Chinese passages independently read: technologies/brands, overseas reach, shareholder/tax/donation declarations, future outlook and dated signatures, macro/industry production-sales-export statistics, policy chronology, phones/servers, business revenue and R&D, and technology performance.',
        'scope_limit': 'L353–355 and L367–369 are each one multiline signature source. L333 and L403 retain the authorized Markdown heading topology even where the topic differs from the preceding English heading; no external PDF or translation-based regrouping. Cross-page paragraphs stay one original source.',
        'not_applicable': 'Only the L371 caption 汽車照片 is checked, with no image reading or inferred visual content. English and Chinese printed assertions are separate sources, not automatically deduplicated translations.',
        'oracle_findings': [{
            'lines': [[353, 355], [367, 369]],
            'original': ['Wang Chuan-fu\nChairman\nShenzhen, the PRC, 24 March 2025', '主席\n王傳福\n中國深圳，二零二五年三月二十四日'],
            'independent_requirement': 'Each complete multiline signature source owns its actual three physical lines in order. Interior raw obligations must remain linked to this same original source, never treated as blank Markdown controls.',
            'observed_defect': 'The old Oracle associates obligations by source first line only, then rejects interior raw source lines as supposedly unreviewed blank separators although the complete content source was checked.',
            'first_failure_function': 'tests.validation.lite_source_oracle.check_fixed_source_graph, obligation case assignment and formatting branch.',
            'review_status': 'oracle_multiline_binding_repaired_and_revalidated',
            'resolution': 'Independent source overrides transcribe all six physical lines including hard-break and emphasis controls. Same-path contained raw obligations are bound only after the full actual multiline range and exact physical text are checked; no separator or N/A waiver.',
        }],
    },
}
