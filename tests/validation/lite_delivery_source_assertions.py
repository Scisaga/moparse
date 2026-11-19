"""Independent selected text, grouping and measurement witnesses for Lite selections."""

IEA = "iea-adoption-ai-types-p025-031"
HIGHLIGHTS = "pingan-business-highlights-p012-013"
CARE = "pingan-health-senior-care-p025-030"
COVER = "spdb-cover-declaration-p001-002"

REVIEW_ASSERTIONS = {
    COVER: ("1200454112", [1, 2], [(1, 11), (13, 23)], """
1|H1|上海浦东发展银行股份有限公司非公开发行优先股募集说明书概览
3|P|股票简称：浦发银行~股票代码：600000
5|P|注册地址：上海市中山东一路12号
7|C|封面印章
9|P|联席保荐机构/联席主承销商~中信证券股份有限公司~国泰君安证券股份有限公司
11|P|联席主承销商~高盛高华证券有限责任公司~中国国际金融有限公司~瑞银证券有限责任公司
13|H2|声明
15|P|全体董事、监事、高级管理人员~不存在任何虚假记载、误导性陈述或重大遗漏~真实、准确、完整
17|P|公司负责人、主管会计工作负责人及会计机构负责人~财务会计报告真实、完整
19|P|中国证监会~不表明~实质性判断或保证~也不表明~投资者的收益~任何与之相反的声明均属虚假不实陈述
21|P|《证券法》~发行人自行负责~投资风险~投资者自行负责
23|P|投资者如欲申购~申购前~募集说明书全文~发行人的日常信息披露文件
"""),
    IEA: ("complex-iea-energy-ai-2025", list(range(25, 32)),
          [(494,506),(508,518),(520,530),(532,546),(547,558),(560,572),(574,574),(576,580)], """
494|P|Since 2022~around 40%~United States and the United Kingdom~400 million weekly active~February 2025~1 million~five days~2-10 months
496|P|online population~over 50%~at least weekly~Brazil, India, Indonesia, Kenya and Pakistan~less than one in three~overall adoption~Chapter 5
498|H4|Figure 1.5. Growth in the use of digital technologies in the workplace since the year of first commercial release, United States
500|C|Figure 1.5
502|P|rapid uptake~enabled by~US workplaces
504|P|personal computers~1981~first IBM~Internet~1995~commercial traffic~generative AI~2022
506|P|Sources~IEA analysis~Bick et al. (2024)
508|P|data analysis and forecasting~cybersecurity~Figure 1.5~OECD~15% in 2020~40% in 2024~Figure 1.6~12 percentage points~30 percentage points~USD 60 000~purchasing power parity~10 percentage points~20 percentage points
510|H4|Figure 1.6. AI adoption rates by firm size in OECD countries and AI adoption rates by firm size compared to GDP per capita of the firm’s home country
512|C|Figure 1.6
514|P|larger firms~higher-income countries~smaller firms~lower-income countries
516|P|PPP = purchasing power parity
518|P|IEA analysis~OECD (2024)~World Bank (2024)
520|P|European Union~Figure 1.7~language and data analysis~ICT security~robotics~logistics~structure of the sample~Chapter 3~Chapter 4
522|H4|Figure 1.7. Percentage of large firms reporting using AI by application type and business function, European Union, 2024
524|C|Figure 1.7
526|P|wide range of applications~across business functions
528|P|IEA analysis~Eurostat (2025)
530|P|missing expertise~more than 250 people~Chapter 5~Privacy and legal~Figure 1.8~Chapter 3~did not rate highly
532|H4|Figure 1.8. Percentage of large firms reporting not using AI by reason, European Union, 2024
534|C|Figure 1.8
536|P|Missing expertise~dominant reason~privacy and legal concerns
538|P|IEA analysis~Eurostat (2025)
540|H3|1.3 What is AI?
542|P|no single and universally accepted~human intelligence~explicitly programmed~learning from data~through training
544|P|three archetypes
546|I|Rules-based or symbolic AI~rules and logic~less well-defined~1990s~DeepBlue~1997~difficult to scale~highly labour intensive
547|I|Machine learning and reinforcement learning~without being explicitly programmed~statistical models~trial and error
548|I|Neural networks and deep learning~interconnected nodes~number nine~multiple “hidden”~bank cheques~early 1990s
550|P|high computational requirements~lack of data~2000s~training algorithms~hundreds of billions~trillions of data points~10²⁴
552|P|combination of techniques~no black-and-white distinction
554|H4|1.3.1 Types of AI
556|P|kinds of tasks~overlaps~commonly used terms
558|P|Predictive AI~future outcomes~predictive maintenance~AlphaFold~two-dimensional sequence~Chapter 4~GraphCast~classical physics
560|P|Generative AI~generating new content~text, images, audio and video~ChatGPT~energy needs~Chapter 2
562|I|Language models~text inputs~text outputs
563|I|Multimodal models~one or more non-text forms~various forms
564|I|Large reasoning models~complex, multistep~coding or mathematics~inference-time scaling~test-time scaling~o1~R1
566|P|Computer vision~visual data~deep learning~object detection~self-driving cars~medical imaging
568|P|Physical or embodied AI~classical industrial robots~open-ended~drones to inspect~laboratories~battery chemistries~Chapter 4
570|P|Agentic AI~autonomous “agents”~virtual environments~voice assistants~buildings~charging of electric vehicles
572|H4|1.3.2 The AI supply chain
574|P|geographically concentrated~very international~small town~rare earth minerals~transistors~hundreds of millions of dollars~atomic scales~high-purity sand
576|P|Large-scale AI models~OpenAI, Meta, Google (Alphabet), MistralAI, NVIDIA and Baidu~United States~dominant position
578|P|on-device~at the edge~too complex~high-bandwidth~backup power~Northern Virginia~Shanghai~Frankfurt
580|P|CPUs~GPUs~TPUs~parallel processing~NVIDIA, Broadcom, AMD and Intel~TSMC and Samsung Foundry~Chinese Taipei and Korea~65%~2024
"""),
    HIGHLIGHTS: ("complex-pingan-2024-annual", [12,13], [(372,438),(440,500)], """
372|H2|Business Highlights
374|H3|1. Steady overall business
376|I|OPAT attributable to shareholders of the parent company~RMB121,862 mn
378|P|OPAT attributable to shareholders~RMB121,862 million~up 9.1% YoY
380|P|Net profit attributable~RMB126,607 million~up 47.8% YoY
382|P|Revenue~RMB1,141,346 million~up 10.6% YoY
384|P|Revenue grew 12.6%~RMB1,028,925 million~2024~Accounting Standards for Business Enterprises~Ministry of Finance
386|H3|2. Cash dividends have risen for 13 consecutive years
388|I|YoY growth in full-year DPS~5%
390|P|Proposed 2024 final dividend~RMB1.62 per share in cash
392|P|Full-year cash dividend will be~RMB2.55 per share~up 5% YoY
394|P|Cash dividend payout ratio~OPAT attributable~will be 37.9%
396|H3|3. Life & Health develops steadily with enhanced channels and high quality
398|I|YoY growth in Life & Health NBV~28.8%
400|P|Life & Health NBV increased 28.8% YoY
402|P|13-month persistency ratio~3.6 pps YoY
404|P|Agent channel NBV~26.5% YoY
406|P|Bancassurance channel NBV~62.7% YoY
408|P|Ping An Life’s sales agents~3 consecutive quarters~363 thousand
410|P|YoY growth in NBV~like-for-like~end-2023 assumptions
412|H3|4. Ping An P&C’s steady revenue growth and good business quality
414|I|COR of Ping An P&C~98.3%
416|P|Insurance revenue~RMB328,146 million~up 4.7% YoY
418|P|Net profit~RMB15,021 million~up 67.7% YoY
420|P|Overall COR improved by 2.3 pps~98.3%
422|P|Auto insurance COR~98.1%~better than the market average
424|P|No.1 Brand~auto insurance~Ministry of Industry and Information Technology~14 consecutive years~highest consumer protection rating
426|H3|5. Excellent insurance funds investment results
428|I|Comprehensive investment yield~5.8%
430|P|Comprehensive investment yield~5.8%~up 2.2 pps YoY
432|P|Life & Health comprehensive investment yield~6.0%~up 2.4 pps YoY
434|P|10-year average net investment yield~5.0%
436|P|10-year average comprehensive investment yield~5.1%
438|C|Photograph
440|H3|6. Ping An Bank keeps steady business performance and asset quality
442|I|Net profit of Ping An Bank~RMB44,508 mn
444|P|Net profit was RMB44,508 million
446|P|Non-performing loan ratio was 1.06%
448|P|Provision coverage ratio was 250.71%
450|H3|7. Integrated finance-enabled core competitive moat and customer development
452|I|Retention of customers holding 4+ contracts~98.0%
454|P|Retail customers increased 4.7% YTD~242 million
456|P|25.6% of customers~4 or more contracts~98.0% retention
458|P|72.2% of customers~5 or more years~94.7% retention
460|H3|8. Differentiation-enabled core businesses under health & senior care strategy
462|I|Ping An Life’s NBV~customers entitled~benefits: ~70%
464|P|partnered with 100%~top 100 hospitals and 3A hospitals
466|P|Customers entitled~about 70%~Ping An Life’s NBV
468|P|Medical, Nursing, Housing, and Entertainment Alliances~home-based~unveiled in 5 cities
470|P|PKU Healthcare Group~positive trend~operational improvement
472|H3|9. Strong offline customer development and service capabilities
474|I|Sales service team members~1.3 mn+
476|P|over 7,000 outlets~over 1.3 million~330 cities nationwide
478|H3|10. CSRs, green development and rural vitalization
480|I|Cumulative investment to bolster the real economy~RMB10.14 trn
482|P|Cumulative investment~nearly RMB10.14 trillion
484|P|Green investment of insurance funds~RMB124,712 million
486|P|Green loan balance~RMB157,762 million
488|P|Green insurance premium income~RMB58,608 million
490|P|Funding for rural industrial vitalization~RMB52,014 million
492|P|MSCI ESG Rating rose to AA~No.1~Asia-Pacific
494|P|Notes:
496|P|(1)~Company’s business results for 2024
498|P|(2)~may not match~due to rounding
500|C|Photograph
"""),
    CARE: ("complex-pingan-2024-annual", [25,26,27,28,29,30], [(722,743),(745,768),(770,796),(798,816),(818,838),(840,862)], """
722|H2|Health and Senior Care
724|C|Photograph
726|P|online/offline~financial businesses~payer~over ten years
728|P|past decade~online, in-store, in-home and in-company~hundreds~quality assurance
730|I|In-house & external doctors~50K
731|I|Partner hospitals~36K+
732|I|Partner health management institutions~104K+
733|I|Partner pharmacies~235K
735|P|standalone direct value~indirect value~Product + Service~Nearly 63%~242 million~December 31, 2024
737|H3|Contracts per customer
739|C|Contracts per customer
741|H3|AUM per customer
743|C|AUM per customer
745|H3|“HEALTH AND SENIOR CARE ECOSYSTEM” STRATEGY
747|P|over ten years~insurance, health care, investment and technology~coordinated operations~PA GOODDOCTOR
749|P|China’s medical resources supply
751|I|per capita health expenditure (1)~over RMB5,400~Japan’s approximately RMB28,000~Singapore’s approximately RMB26,000
752|I|elderly population (2)~exceeded 210 million in 2023~forecast~over 300 million by 2035~37.44 million~0.95 million
754|P|three fronts~differentiated health and senior care~acts as a payer
756|I|internal service provider~retail financial customers~Ping An Life and Ping An Bank
757|I|employee health management programs~corporate clients~employee benefit products~Ping An Health Insurance
758|I|long-term revenue~online flagship~proprietary medical institutions~mid-range and high-end
760|P|Notes:
762|P|(1)~for 2021~National Bureau of Statistics~Japan and Singapore~World Bank~estimated in RMB
764|P|(2)~Research Report on Aging in China 2023~Japan and Singapore~World Bank
766|P|(3)~aged 65 and above
768|P|online flagship~bridge between payers and providers~retail and corporate~after acquiring PKU~offline medical resources
770|H3|“HEALTH AND SENIOR CARE ECOSYSTEM” PROGRESS
772|P|acts as a payer~retail and corporate~provider side~PKU Healthcare Group~cost-effectiveness and accessibility
774|I|Health insurance premium income~RMB140 bn+
776|P|over RMB140 billion~2024~about 70%~Life’s NBV~over 31%~over 38%
778|H4|Payers
780|P|nearly 67,000 paying corporate clients~over 31 million paying users~12 months ended December 31, 2024~Over 160,000 customers
782|H5|“Finance + health care”:
784|H6|For mid-range and high-end retail customers
786|P|launch in 2021~18 service items~five highlights~over 21 million~2.1 pps~2023~nearly 79%~newly-enrolled
788|I|Ping An Life’s customers who used health management services~21 mn+
789|I|Newly-enrolled customers who used health management services~79%
791|H6|For large and medium-sized corporate clients
793|P|commercial insurance + health care fund + health care service~Nearly 67,000~29 million plus~2024
795|I|Paying corporate clients~67K
796|I|Corporate employees served~29 mn+
798|H5|“Finance + senior care services”:
800|P|home-based senior care~high-end senior care~high-value customers~international standards
802|H6|Home-based senior care
804|P|over 150~75 cities~10-dimensional~Over 160,000~over 70,000~Nursing Alliance~2023~March and August 2024 respectively~SOPs
806|H6|High-end senior care
808|P|six premium~five cities~under construction~Shanghai and Shenzhen~scheduled~second half of 2025
810|H4|Providers
812|H5|Proprietary flagships
814|P|PKU Healthcare Group~Peking University International Hospital~RMB2.48 billion~1.25 million~1,306~five general hospitals~eighteen health management centers~ten children’s
816|P|In the future~four business lines~global medical service integration~Mayo Clinic, Cleveland Clinic, and UCLA Health
818|P|Healthy China~will explore~full-cycle health services
820|H6|Unique services
822|P|physical needs, safety needs, and emotional needs~rehabilitative care~smart senior-friendly devices~AI chatbot companions
824|H6|Ping An Family Doctor
826|P|exceeded 14 million~five times per capita in 2024~24/7~Before visits~During visits~After visits~follow-up visits
828|H5|Partner networks
830|P|online, in-store, in-home and in-company~domestic and overseas~commodities and medicines
832|P|about 50,000~over 36,000~all top 100 hospitals and 3A~over 104,000~approximately 235,000~over 35%~over 4,000~10-dimensional
834|P|over 1,300~35 countries~7 of global top 10~56 of global top 100 (1)
836|P|(1)~Newsweek’s World’s Best Hospitals List
838|P|healthtech R&D~over 5,000 diseases~remote consultation~December 31, 2024
840|H3|POSITIVE RESULTS FROM A PROPRIETARY “HEALTH AND SENIOR CARE ECOSYSTEM”
842|H4|Ping An’s proprietary health and senior care ecosystem provides customers with excellent, efficient service experience
844|P|nine medical specialties~24/7~within 60 seconds~no major health care incident~five-star~over 98%
846|H4|Ping An’s health and senior care ecosystem empowers its core financial businesses through customer acquisition and retention
848|P|Ping An Health and PKU Healthcare Group~retail customers~Ping An Life access to service benefits
850|P|Nearly 63%~242 million~December 31, 2024~3.37 contracts~RMB59.9 thousand~1.6 times and 3.8 times~not entitled
852|H5|Core business enablement case 1
854|P|insurance + service~life insurance policies~online, in-store, in-home and in-company~health account~financial account~customer retention
856|H5|Core business enablement case 2
858|P|Ping An Family Doctor~maintains health records~real time~Zhen Xiang RUN~five highlights~critical illness management~worry-free, time-saving, and money-saving
860|P|In the long run~core insurance business~family doctors~user retention~free-to-paid conversion
862|P|premium health and senior care resources~service network~economies of scale~long-term profit center
"""),
}

# A short printed label binds the complete field, including literal scale,
# rounding, inequality and terminal punctuation. Long sentences can remain
# ordered content; a typed predicate must retain all of its complements.
REVIEW_TYPED_ASSERTIONS = {}
REVIEW_TYPED_ASSERTIONS[COVER, 3] = [("", "股票简称", "浦发银行", {}), ("", "股票代码", "600000。", {})]
REVIEW_TYPED_ASSERTIONS[COVER, 5] = [("", "注册地址", "上海市中山东一路12号。", {})]
REVIEW_TYPED_ASSERTIONS[COVER, 9] = [
    ("", "联席保荐机构/联席主承销商", "中信证券股份有限公司、国泰君安证券股份有限公司。", {})]
REVIEW_TYPED_ASSERTIONS[COVER, 11] = [
    ("", "联席主承销商", name, {}) for name in
    ("高盛高华证券有限责任公司", "中国国际金融有限公司", "瑞银证券有限责任公司")]
for sample, fields in {
    IEA: [(528, "Source", "IEA analysis based on data from Eurostat (2025)."),
          (538, "Source", "IEA analysis based on data from Eurostat (2025).")],
    CARE: [(730,"In-house & external doctors","~50K."), (731,"Partner hospitals","36K+."),
           (732,"Partner health management institutions","104K+."), (733,"Partner pharmacies","235K."),
           (774,"Health insurance premium income","RMB140 bn+."), (795,"Paying corporate clients","~67K.")],
    HIGHLIGHTS: [(376,"OPAT attributable to shareholders of the parent company","RMB121,862 mn."),
                 (388,"YoY growth in full-year DPS","5%."), (398,"YoY growth in Life & Health NBV","28.8%."),
                 (414,"COR of Ping An P&C","98.3%."), (428,"Comprehensive investment yield","5.8%."),
                 (430,"Comprehensive investment yield","5.8%, up 2.2 pps YoY."),
                 (442,"Net profit of Ping An Bank","RMB44,508 mn."),
                 (452,"Retention of customers holding 4+ contracts","98.0%."),
                 (462,"Ping An Life’s NBV from customers entitled to health & senior care benefits","~70%."),
                 (474,"Sales service team members","1.3 mn+."),
                 (480,"Cumulative investment to bolster the real economy","~RMB10.14 trn.")],
}.items():
    for line, label, value in fields:
        REVIEW_TYPED_ASSERTIONS[sample,line] = [("", label, value, {})]

for line, subject, predicate, value, qualifiers in [
    (394,"Cash dividend payout ratio based on OPAT attributable to shareholders of the parent company","be",
     "be 37.9%",{"modality":"will","polarity":"positive"}),
    (400,"Life & Health NBV","increase","28.8% YoY",{"polarity":"positive","tense":"past"}),
    (434,"10-year average net investment yield","be","5.0",{"unit":"%","polarity":"positive","tense":"past"}),
    (436,"10-year average comprehensive investment yield","be","5.1",{"unit":"%","polarity":"positive","tense":"past"}),
    (444,"Net profit","be","RMB44,508 million",{"polarity":"positive","tense":"past"}),
    (446,"Non-performing loan ratio","be","1.06",{"unit":"%","polarity":"positive","tense":"past"}),
    (448,"Provision coverage ratio","be","250.71",{"unit":"%","polarity":"positive","tense":"past"}),
    (454,"Retail customers","increase","4.7% YTD",{"polarity":"positive","tense":"past"}),
    (484,"Green investment of insurance funds","be","RMB124,712 million",{"polarity":"positive","tense":"past"}),
    (486,"Green loan balance","be","RMB157,762 million",{"polarity":"positive","tense":"past"}),
    (488,"Green insurance premium income","be","RMB58,608 million",{"polarity":"positive","tense":"past"}),
]:
    REVIEW_TYPED_ASSERTIONS[HIGHLIGHTS,line] = [(subject,predicate,value,qualifiers)]

REVIEW_REPRESENTATION_POLICIES = {key: "typed" for key in REVIEW_TYPED_ASSERTIONS}

# Predicate tense, printed unit and the growth endpoint have separate
# source relations. Each one must belong to the same sentence and metric.
REVIEW_SOURCE_OVERRIDES = {
    (HIGHLIGHTS,line): {"binding_qualifiers": {"tense":"past"}}
    for line in (400,434,436,444,446,448,454,484,486,488)
}
REVIEW_SOURCE_OVERRIDES[COVER, 11] = {"entity_list_separator": "、"}
for line, subject, expression in [(434,"10-year average net investment yield","5.0%"),
                                   (436,"10-year average comprehensive investment yield","5.1%"),
                                   (446,"Non-performing loan ratio","1.06%"),
                                   (448,"Provision coverage ratio","250.71%")]:
    REVIEW_SOURCE_OVERRIDES[HIGHLIGHTS,line]["printed_predicate_quantity"] = (subject,"was",expression)

REVIEW_REQUIRED_RELATIONS = {
    (HIGHLIGHTS,454): [
        {"type":"narrative_prepositional_attachment","left":{"preposition":"to","complement":"242 million",
         "attachment":{"kind":"predicate","head":"increased","attribute":"increase"}}},
        {"type":"narrative_quantity_scope","left":{"operator":"eq","value":"4.7","unit":"%"}},
    ],
}
