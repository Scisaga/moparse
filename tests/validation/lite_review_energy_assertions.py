"""Third-batch source Oracle declarations, authored from selected text only.

These are test expectations, never runtime parsing answers. Every selected
paragraph was read in full before fresh compilation. Figure checks cover
printed captions and notes only; no image content is inferred.
"""

REVIEW_ASSERTIONS = {
    'bis-endnotes-technical-annex-p052-057': ('complex-bis-economic-2024', [52, 53, 54, 55, 56, 57],
        [(962, 978), (979, 984), (986, 1010), (1012, 1030), (1032, 1050), (1052, 1070)], '''
962|H3|Endnotes
964|I|See Doornik et al (2023).
965|I|See Hardy et al (2024).
966|I|See Shapiro (2022).
967|I|See Miranda-Pinto et al (2023).
968|I|long-run trend~First~higher income elasticity of services~as income per capita rises~Baumol cost disease~higher-productivity manufacturing~similar wages~productivity gap~Third~international competition~goods~services
969|I|See Borio et al (2023).
970|I|Ampudia et al (2024)~similar results for the United States~Heise et al (2022)
971|I|Borio et al (2019)~bandpass filters~eight to 32 years~inflation-adjusted credit~credit-to-GDP ratio~real property prices
972|I|See also Borio (2014).
973|I|See also de Soyres et al (2023).
974|I|Private equity~ownership stake~not currently traded~Private credit~non-bank financial institutions~highly leveraged~cannot borrow~Box D
975|I|See also BIS (2023).
976|I|Inefficient resource allocations~in addition to macroeconomic factors~could also~IMF (2024a, Chapter 3)~Andrews et al (2015)
977|I|Acemoglu (2024)~may generate only a modest boost~0.5–0.7% over 10 years~increasing inequality~capital and labour incomes~Brynjolfsson et al (2023)~experimental setting~customer service~14% on average
978|I|See BIS (2023).
979|I|Policy credibility~trust in public policy~once lost~difficult to regain~Carstens (2024)
980|I|See Benigno et al (2024).
981|I|See BIS (2023) for more in-depth discussion.
982|I|See IMF (2024b).
983|I|Average primary deficits~public debt to GDP constant~next five years~Median of CA, DE, FR, IT, GB, JP and US~April 2023 and April 2024~Graph 16~methodology and assumptions
984|I|See OECD (2023).
986|H3|Technical annex
988|P|Graph 2.A:~Okun’s law~negative relationship~output~unemployment~Q1 2022 and Q4 2023~linear regression~Q1 2000 and Q4 2019~subject to data availability
990|P|Graph 2.B: AEs = AU, CA, EA, GB, JP and US.
992|P|Graph 2.C:~Median values across NFC per country~GDP-PPP weighted~20 EA member states~six other AEs~nine Asian EMEs~six Latin American~EA = AT, BE~SK.~Other AEs = AU, CH, GB, NO, NZ and SE.~Asian EMEs = HK, ID, IN, KR, MY, PH, SG, TH and VN.~Latin America = AR, BR, CL, CO, MX and PE.
994|P|Graph 4.A:~yearly averages~GDP-PPP weighted~AEs = CA, CH, DK, EA, GB, JP, NO, SE and US~EMEs = BR, CL, CO, CZ, HU, IL, KR, MX, PH, PL, SG and ZA
996|P|Graph 4.C: Other AEs = AU, CA, DK, GB, NO, NZ and SE; GDP-PPP weighted averages.
998|P|Graph 5.A:~sectoral personal consumption expenditures~Q3 2023~except for NL and SE~Q4 2023
1000|P|Graph 5.B:~linear regression~Q4 2000 to Q3 2022~Annualised quarter-on-quarter headline inflation~own lag~job vacancy rate~West Texas Intermediate~Global Supply Chain Pressure Index~one-year-ahead inflation expectations~output gap~year-on-year changes
1002|P|Graph 5.C:~AU, CA, DE, ES, FR, GB, IT, JP, KR and US since 1990~fourth lag and the output gap~peak to latest (Q1 2024)~US~Q2 2022~EA~Q1 2023~simple average across DE, ES, FR and IT
1004|P|Graph 6.C:~Historical~2 January 2010 until 31 May 2024~Latest = 31 May 2024~AEs = AU, CA, CH, EA, GB, JP and NZ~EMEs = BR, CL, CN, CO~ZA.~Alphabet, Amazon, Apple, Meta, Microsoft, Nvidia and Tesla~median is shown
1006|P|Graph 7.A:~option-adjusted spread~benchmark yield curve~value of embedded options
1008|P|Graph 7.B:~end of the next calendar year~Federal Reserve and the financial market~vertical axis~three-month moving average~Bloomberg inflation surprise index~horizontal axis~June 2021–June 2024
1010|P|Graph 7.C: Weekly average for federal funds rate futures.
1012|P|Graph 8.A:~Goldman Sachs Financial Conditions Index (FCI)~risk-free interest rates~long- and short-term~exchange rates~equity valuations~credit spreads~impact of each variable on GDP~100 indicates average~higher (lower)~tighter (looser)
1014|P|Graph 8.B: Monthly averages.~VIX = Chicago Board Options Exchange (CBOE) Volatility Index.~VXTLT = CBOE 20+ Year Treasury Bond ETF Volatility Index.
1016|P|Graph 8.C:~GDP-PPP weighted averages~Asian EMEs = CN, ID, IN, KR, MY, PH, SG, TH and VN~Latin America = BR, CL, CO, MX and PE~other AEs = AU, CA, CH, EA, GB, NO, NZ and SE~other EMEs = CZ, DZ, HU, IL, KW, PL, RO and ZA
1018|P|Graph 9.A: Net percentage of bank loan officers reporting they are tightening lending standards.
1020|P|Graph 9.B: Net percentage of bank loan officers reporting they are seeing increased loan demand.
1022|P|Graph 10.A:~Simple averages of the price-to-book ratio~EA, other AEs and EMEs~EA = AT, BE, DE, ES, FI, FR, IT and NL~Other AEs = AU, CA, CH, DK, GB, JP, NO, NZ and SE~EMEs = AE, AR, BR~ZA.
1024|P|Graph 10.B:~JPMorgan GBI-EM broad traded index~JPMorgan Emerging Market Bond Index~EPFR net equity and bond fund flows~month prior to the first policy rate cut~Mar 2024~GDP-PPP~increase indicates an appreciation of the dollar~equally weighted~Mar 1983, Mar 1988, Feb 1994 and Jun 1999~since 1991~since 1992~since 2002~since 2003~EMEs = BR, CL, CN~ZA.
1026|P|Graph 11.A:~GDP-PPP weighted~six-month moving averages~seasonally adjusted~AEs = AU, CA, CH, DK, EA, GB, JP, NO, NZ, SE and US~EMEs = BR, CL, CO, CZ, HU, IL, KR, MX, PE, PH, SG and ZA~Q1 2015–Q4 2019
1028|P|Graph 11.B:~deflating nominal wages with headline CPI~National definitions~Four-quarter moving averages~Q1 2013–Q4 2019~CA, CZ, EA, GB, HU, JP, MX, NO, SE and US
1030|P|Graph 11.C:~sectoral data from Eurostat~already aggregated across countries~Q1 2009 and Q2 2023~Ampudia et al (2024)
1032|P|Graph 12.A:~Borio (2014)~frequency-based (bandpass) filters~real credit~credit-to-GDP ratio~real house prices~country-specific means and standard deviations~simple averages~AEs = AU, BE~US.~EMEs = BR, CL~ZA.
1034|P|Graph 12.B:~US financial cycle peaks~Q4 1987, Q3 2005 and Q2 2023~Median across the episodes~for GDP~for loan impairment ratio
1036|P|Graph 13.A:~Excess savings~household savings rate is above trend~Hamilton (2018) filter~time-varying trend~starts in Q1 2020
1038|P|Graph 13.B: Annual data, 2023 if available, 2022 otherwise.~EMEs = AR, BR~Other AEs = AT, AU~SK.
1040|P|Graph 13.C: 2023 or latest available.~Definitions vary by country~New mortgages~AU, BE, CA, FR, GB, HK, IE, LU, NL and SA~Existing mortgages~KR and NZ~three months for KR and LU~one year for NL~four months to three years for KR~four months to two years for LU~one to five years for NL~five to 10 years for KR~duration of the loan for FR and HK
1042|P|Graphs 14.A and 14.C:~AU, CA, DE, DK, ES, FI, FR, GB, IT, JP, NL, NO, SE and US
1044|P|Graph 14.B:~deviations from baseline projections~averaged over 2024–26~Bayesian VAR~GDP growth~real commercial property~real residential property~credit to the non-financial~debt service ratio~policy rate~real equity price~Q1 1981 to Q3 2023~sign restrictions~immediate fall~decline in GDP growth with a lag
1046|P|Graph 14.C: Latest is Q4 2023 for all countries except DK and NL (Q3 2023).
1048|P|Graph 15.A: Loans considered are leveraged loans. Spreads to maturity.
1050|P|Graph 15.B:~Shanghai interbank offered rate (Shibor)~secured overnight financing rate (SOFR)
1052|P|Graph 15.C:~latest relative to 1 June 2023~China beta~daily log changes~Chinese index~controlling for the US index~7 January 2002 and 1 June 2023
1054|P|Graph 16.A: IMF projections~assumed policy paths~when specific budget information is lacking~Other AEs = AU, CA, CH, GB and SE~Other EMEs = AR, BR~ZA.
1056|P|Graph 16.B: Automatic debt dynamic is calculated as (rₜ − gₜ) × Debtₜ₋₁~five-year rolling average~10-year government bond yields~GDP deflator~annual real GDP growth~From 2024~assumed to stay constant~CA, DE, FR, GB, JP, KR and US~IMF calculations~assumed policy paths~when specific budget information is lacking
1058|P|Graph 16.C: Latest is 31 May 2024. CDS 10-year maturity.
1060|P|Graph 17: GDP-PPP weighted averages~Euro area = AT, BE, DE, EE, ES, FR, IE, IT, LT, NL, PT, SI and SK~other AEs = AU, CA, DK, GB, JP, NO, NZ and SE~EMEs = CZ, HU, IL, MX and PL
1062|P|Graph 18.A:~44 economies~mean value of real GDP growth~each period of time and each country~AR, AT, AU~US and ZA
1064|P|Graphs 18.B and 18.C: Labour productivity is defined as gross value added per person employed.
1066|P|Graph 18.C:~country sample~AT, AU, BE~US and ZA~Dots represent country-year pairs~simple regression~statistically significant at the 1/5/10% level
1068|P|Graph 19.A:~median and interquartile range~CA, CH, DK, EA, GB, JP, KR, NO, SE and US~goods excluding food and energy
1070|P|Graph 19.B:~annual inflation at the end of each year~median and interquartile range~AT, BE, DE, ES, FI, FR, IT, NL and PL~cumulated response~horizons (in quarters)~industrial and services sectors~1 percentage point increase in hourly wages~Q1 2009 to Q2 2023~Ampudia et al (2024)
'''),
    'iea-energy-manufacturing-p037-040': ('complex-iea-energy-ai-2025', [37, 38, 39, 40],
        [(641, 655), (657, 657), (659, 667), (669, 685), (687, 701)], '''
641|P|Ultimately~benchmark tests do not yet~comprehensively measure~vis-à-vis a human~for all their limitations~complement data on real-world deployment
643|H4|Figure 1.11. Accuracy of AI models in selected benchmarks, 2018-2024
645|C|Figure 1.11
647|P|several limitations~carefully interpreted~improved performance~over time
649|P|Notes:~y-axis~accuracy of models~does not compare~vis-à-vis a human~HumanEval (Code Generation)~Graduate-Level Google-Proof Q&A Benchmark (GPQA)~Mathematics Assessment of Textual Heuristics (MATH) Level 5~Visual Commonsense Reasoning (VCR)
651|P|Sources: IEA analysis~EpochAI (2025a)~Papers With Code (2025)~Stanford University (2024)
653|H3|1.4 Energy for AI and AI for energy
655|P|improve efficiency, reduce costs and drive innovation~weather forecasting~wind and solar photovoltaic~transmission lines~new battery chemistries~Chapters 3 and 4
657|P|data centres consumed around 1.5%~2024~AI is only one~range of workloads~Chapter 5~10-25 megawatts (MW)~100 MW or more~100 000 households~Historically~spatial terms~local grids
659|H4|Figure 1.12. Data centre annual electricity consumption in household electricity consumption equivalents and the spatial concentration of various facilities versus proximity to urban areas
661|C|Figure 1.12
663|P|geographically concentrated~around cities~100 MW~100 000 households
665|P|Notes: km = kilometre.~conventional~25 MW~hyperscale~100 MW~under-construction~around 2 000 MW~planned~5 000 MW~inverse of the linearised Nearest Neighbour Index~observed mean distance~expected mean distance
667|P|Ireland~around 20%~metered electricity supply~6 states~United States~over 10%~Virginia~25%~multiple types of workloads~AI~life cycle
669|H4|Figure 1.13. Global map of large data centre clusters, 2024
671|C|Figure 1.13
673|P|large clusters~potentially~local electricity systems
675|P|Notes: GW = gigawatt.~within 100 km~ten largest clusters~Pearl River Delta~Guangzhou, Shenzhen and Hong Kong (China)
677|P|Source: IEA analysis based on data from OMDIA (2025).
679|H4|1.4.1 AI model life cycle and energy consumption
681|H5|Hardware manufacturing
683|P|manufacturing~less energy than the operation phase~3 nanometre (nm)~around 2.3 megawatt hours (MWh) per wafer~Garcia Bardon, et al., 2021~more than 10 MWh~more than 80 MWh~five-year lifetime~60%~wafer and semiconductor~deposition, lithography and etching~remaining 40%~water preparation or cooling
685|P|higher complexity of metal layers~increases manufacturing electricity demand despite overall efficiency gains~embodied energy per operation decreases~Schneider, et al., 2025
687|H4|Figure 1.14. Electricity intensity of wafer production by process step and node type and server electricity demand
689|C|Figure 1.14
691|P|more complex chip types~especially for lithography and deposition~less than 20%~life-cycle demand
693|P|Notes: nm = nanometre.~“Other”~cooling and water preparation~“Operation”~five years
695|P|Sources: IEA analysis~Garcia Bardon, et al. (2021)~Boavizta (2021)~Dell (2019)
697|P|More than 70%~East Asia~BCG and SIA, 2021~more than 100 terawatt hours (TWh)~per year~Greenpeace, 2023~around 1%~global industrial~TSMC~more than 20 TWh in 2023~almost 10%~Chinese Taipei~Most semiconductors~other purposes~data centres and especially AI~years to come
699|P|Indirect emissions~most significant~coal-fired~high emissions footprint~Minor use of fossil fuels~around 5%~process gases~direct emissions
701|P|construction~transport of intermediate materials~minor impact~including the materials~less than 2%~life-cycle emissions
'''),
    'iea-inference-energy-boxes-p043-048': ('complex-iea-energy-ai-2025', [43, 44, 45, 46, 47, 48],
        [(732, 743), (745, 745), (747, 753), (755, 755), (757, 761), (763, 773), (775, 785), (787, 799), (801, 811)], '''
732|H5|Model use
734|P|After training and fine tuning~deployed~Each time~ChatGPT~similar high-specification GPU-accelerated servers~query (or “inference”)~numerous factors
736|I|Input query size and output answer length:~longer~more compute~more electricity
737|I|Model size: larger models~more compute~more electricity intensive~all other things being equal
738|I|Input and output mode:~video and image generation~more compute intensive~than text generation~Figure 1.16
739|I|Implementation of algorithmic efficiencies:~mixture of experts (MoE)~selectively activate only~pertinent~saving~while preserving model performance
740|I|Degree of inference-time scaling:~OpenAI’s o1~DeepSeek’s R1~reasoning or planning~“thinking”~before responding~dramatically increase~energy cost
741|I|Hardware implementation:~B200 GPU is 60% more energy efficient~FLOP/watt~H100~80%~A100~EpochAI, 2025c~substantially influence
743|P|tyre pressure~road surface~temperature~wind speed~driving speed and style~air conditioning or heating~20% higher~Worldwide Harmonised Light Vehicles Test Procedure~3.5 times higher~plug-in electric hybrid~do not charge~full-electric mode~European Commission, 2024
745|P|Similar caveats~batch sizes, key-value cache management and attention management.⁵~lack of transparency~impossible to measure~hard to estimate~AI as a whole~informed choices~Nonetheless~benchmarks
747|H4|Box 1.2. Did DeepSeek change the outlook for AI electricity demand?
749|P|DeepSeek-R1~20 January 2025~one week later~chip designer~down 20%~manufacturing equipment~down 6%~energy companies~around 20%~uncertainty~whether~changed the outlook
751|P|MoE~activated model size by 95%~preserving performance~contextual relationships~most important words~rest.⁶~parallel, not sequentially.⁷~“the cat sat”~“on the mat”~single computational step
753|P|drive down~training and use~countervailing~First, lower costs may incentivise greater use~Second~DeepSeek-R1 and OpenAI’s o1~more energy intensive~“inference-time scaling”~better answers~reasoning or planning~extremely inefficient~knowledge retrieval or summarisation
755|P|three themes~First~software and a hardware issue~Second~incentivise greater use~more compute use~rebound effect~Third~right model for the right task~price and information~business models~regulatory and policy
757|P|⁵ Batching~grouping tasks~rather than sequentially~dishwasher fully loaded~Key-value cache~GPU memory~reading and writing~energy intensive~flash attention~separate, more efficient chunks
759|P|⁶ This approach is called multi-head latent attention (MLA).
761|P|⁷ This is known as multi-token prediction (MTP).
763|P|open-source models~generative AI tasks.⁸~only the GPU energy costs~H100 GPUs~Figure 1.16 and Figure 1.17~highly controlled experimental~real-world implementations are likely to differ~Figure 1.18~batching
765|H4|Figure 1.16. Indicative inference electricity consumption for selected generative AI tasks in experimental conditions and the electricity consumption of charging consumer electronics
767|C|Figure 1.16
769|P|single short video~charging a laptop two times
771|P|Notes: Text generation, low = Yi-1.5 9B~9 billion~high = Llama 3.3~70 billion~SD-XL 1.0-base~CogVideoX-5b~6 seconds long and 8 frames per second~Only the GPU electricity consumption~most reliable
773|P|⁸~Dr Sasha Luccioni~All errors, omissions and conclusions~IEA alone
775|P|under test conditions~small language model~0.3 Wh~medium-sized~5 Wh~Image generation~1.7 Wh per task~Video~115 Wh~6 seconds~8 frames per second~mobile phone or laptop~15 Wh and 60 Wh, respectively
777|H4|Figure 1.17. Indicative inference electricity consumption across different model types for text generation tasks in experimental conditions
779|C|Figure 1.17
781|P|Model design and model choice~electricity intensity
783|P|Notes: LM = language model; MoE = mixture of experts.~SmolLM2-1.7B-Instruct~Yi-1.5~Llama 3.3~70 billion~Mixtral-8x 22B~DeepSeek-R1~Only the GPU~estimated~same size~specific sample of prompts~O'Donnell, 2025
785|P|sizes and set-ups~Larger models~more energy~same text generation task~1.7 billion parameters~0.1 Wh~40 times more parameters~more than 40 times more electricity~around 4 Wh~two-and-a-half times~only around 45% more~DeepSeek-R1~maths and coding
787|P|reasoning model~simple text generation~twice as much electricity~comparable size~Figure 1.17~model design and choice
789|P|real world~batching~independent inputs~in parallel~otherwise be underutilised~increasing per-token energy consumption
791|H4|Figure 1.18. Impact of batching on electricity consumption per task for inference across various generative AI models
793|C|Figure 1.18
795|P|batching halve the electricity consumption per task
797|P|Notes: LM = language model; MoE = mixture of experts; e = estimated.~Only the GPU~most reliable~batch size~number of parameters~normalised GPU electricity consumption per token~Argerich and Patiño-Martinez, 2024
799|P|efficiency gains~diminishing returns~increasing batch size~constrained by the memory capacity~impractical for very large models~smaller memory size
801|H4|Box 1.3. A bag of heuristics to go from tasks to TWh
803|P|heuristics (rules-of-thumb)~not overly simplified~right situation~electricity demand~potential output
805|P|projected to grow by several hundred TWh~Chapter 2~consume 100 TWh~in 2023~Google, Amazon, Meta and Microsoft~combined~90 TWh
807|I|large language model~optimised implementation~more than 4 250 trillion words~100 TWh~110 million copies~Encyclopaedia Britannica
808|I|image generation~around 55 trillion images~around 100 TWh
809|I|video generation~950 million hours~100 TWh~Netflix~94 billion hours~second half of 2024
811|P|rough orders of magnitude~100 TWh~multimodal~text, image, video~rough approximations~real-world~more efficient~commercial models~more powerful~possibly more energy intensive~open-source models
'''),
    'iea-rise-ai-p021-024': ('complex-iea-energy-ai-2025', [21, 22, 23, 24],
        [(430, 446), (448, 460), (462, 462), (464, 476), (478, 478), (480, 492)], '''
430|H3|1.2 The rise of AI
432|P|at least the 1950s~optimism and pessimism~“AI winters”~generative AI~techniques, costs and technology~Figure 1.1
434|I|computing power~decline in cost~today with 2006~GPU~per unit of computation~decreased by more than 99%
435|I|availability and quality of data~Internet and connectivity~nearly 30 000 times since 2008
436|I|architectures and algorithms~deep neural networks~section 1.3~computational power~around 350 000 times since 2014
438|P|powerful, capable and flexible~academic research~hundreds of billions of dollars~annually~trillions of dollars~financial market value
440|H4|Figure 1.1. GPU computation cost, 2006-2024, and notable AI model computational training size, 2014-2024
442|C|Figure 1.1
444|P|past decade~cheaper computing~exponentially more data~research breakthroughs~AI model capabilities
446|P|Sources: IEA analysis~EpochAI (2024)~Coyle and Hampton (2024)
448|H4|1.2.1 Surging expectations in financial markets
450|P|United States~November 2022~ChatGPT~end of 2024~65%~growth in market capitalisation~S&P 500~USD 16 trillion~USD 12 trillion~AI-related companies alone~recent volatility~AI-focused start-ups~2024~fourth round~five times higher
452|H4|Figure 1.2. Market capitalisation of S&P 500 companies, November 2022 and November 2024, and median valuations of United States-based start-ups, 2024
454|C|Figure 1.2
456|P|Both listed and unlisted~outpaced non-AI~stock markets~raising valuations
458|P|Notes: MER = market exchange rate.~S&P 500~key AI offerings~pre-money~seed (initial funding~series A (first major round~series B (second major~series C (usually~accelerate expansion
460|P|Sources: IEA analysis~Bloomberg Terminal (n.d.)~Crunchbase (n.d.)
462|P|Alphabet, Amazon, Meta Platforms, and Microsoft~planning as much as USD 300 billion~AI-related capital expenditure in 2025~over 20% higher~total power sector investment~United States~Box 1.1
464|H4|Box 1.1. Rising ICT investment: a longer-term perspective
466|P|capital- and energy-intensive data centres~expectations~future AI demand~earnings~monetisation~energy sector~economic outlook~“bubble”
468|P|ICT~share of gross domestic product (GDP)~United States~highest~three decades~previous peak~2000~“dotcom bubble”~since 2015~corporate software~data centres and networks
470|H5|Figure 1.3. Investment in ICT-related assets and infrastructure as a share of GDP, United States, 1995-2023
472|C|Figure 1.3
474|P|around 5.5% of US GDP~higher than at any other time since the 2000 dotcom bubble
476|P|Source: IEA analysis based on data from US Bureau of Economic Analysis (2024).
478|P|major technological innovations~capital investment~temporarily ran ahead of demand~ultimately proved highly productive~infrastructure~business models~skills~Nikola Tesla’s~1887~nearly 40 years~electricity to overtake steam~US factories~Divine, 1983~doubling~annual productivity improvement
480|P|lead times~much longer than for data centres~Chapter 2~avoid stranded asset risk~clearer understanding~unavoidable uncertainties~economics, uptake and service demand
482|H4|1.2.2 How do households and businesses use AI?
484|P|high-speed Internet~over 90 mobile broadband subscriptions per 100 people~75 subscriptions~five years ago~Half of the world’s population~5G~fixed and mobile broadband~more than three times since 2019~Figure 1.4
486|H4|Figure 1.4. Global digital connectivity indicators and internet traffic, 2019-2024
488|C|Figure 1.4
490|P|foundation for AI~since 2019~total Internet traffic~more than three times
492|P|Source: IEA analysis based on data from ITU (n.d.).
'''),
    'iea-training-energy-p041-042': ('complex-iea-energy-ai-2025', [41, 42],
        [(703, 713), (714, 718), (720, 722), (724, 730)], '''
703|H5|Model training
705|P|learning from data~inputs~output, prediction or action~training data~objectives~grown exponentially~GPT-4~around 4.9 trillion data points~around 22 trillion trillion calculations~2.2e25
707|P|GPUs~maximum rated power~1 000 watts~toaster~GPT-4~25 000 GPUs~around 10 MW~EpochAI, 2024~CPUs, memory, networking equipment and switches.²~cooling~around 22 MW~around 150 high-power electric vehicle charging stations
709|P|GPT-4~around 14 weeks~load factor of 84%~Shehabi, et al., 2024~around 42.4 gigawatt hours (GWh)~around 0.43 GWh per day~28 500 households~advanced economies~70 500 households~emerging market and developing~fine tuning~less computationally intensive~less energy intensive
711|P|varies substantially~size and complexity~hardware configuration~Comprehensive training data are not available~all large AI models developed since 2020~Figure 1.15~methodology
713|I|283 large AI models~EpochAI (EpochAI, 2025b).³~scales with the computational intensity~based only on large AI models~bulk
714|I|maximum training power draw~estimated training duration~multiplying these values~84%~Shehabi, et al., 2024~largest AI model~154 MW⁴~around 310 GWh
715|I|fit a statistical relationship~compute intensity~electricity intensity~EpochAI dataset~compute intensity estimates are available
716|I|neither compute intensity nor maximum training power draw and training duration~extrapolated~average electricity consumption~preceding two steps
718|P|In the absence of better data~at least an order of magnitude~large frontier AI models~around 1 700 GWh (1.7 TWh)~around 0.001% of global electricity~during this period~all sources~0.1%~data centres~during these years
720|P|²~EpochAI~multiplies the GPU power draw by 2.03~non-GPU server hardware~networking, switches and CPUs~NVIDIA DGX H100~further 1.09~non-IT load~https://epoch.ai/data/notable-ai-models-documentation#estimating-power-draw
722|P|³ Large AI models~training compute of 10²³ FLOP~as of 24 March 2025
724|H4|Figure 1.15. Estimated training-related maximum power draw, electricity consumption and cumulative electricity consumption for a set of large AI models since 2020
726|C|Figure 1.15
728|P|largest AI model today~around 154 MW~collectively~estimated at around 1 700 GWh
730|P|⁴ In practice, servers never hit their maximum designed power.
'''),
    'nvidia-definitions-p017': ('complex-nvidia-2025-annual', [17], [(443, 493)], '''
443|H2|DEFINITIONS
445|I|2007 Plan: NVIDIA Corporation Amended and Restated 2007 Equity Incentive Plan
446|I|AC: Audit Committee of the Board
447|I|Additional SY PSUs: PSUs granted in Fiscal 2024 based on annual non-GAAP gross margin performance, with a single-year performance metric (assuming a certain level of annual Non-GAAP Operating Income), vesting over four years
448|I|ASC 718: FASB Accounting Standards Codification Topic 718: Compensation - Stock Compensation
449|I|Base Compensation Plan: Performance goal necessary to earn the target award under the Variable Cash Plan and for the target numbers of SY PSUs and MY PSUs to become eligible to vest
450|I|Board: The Company’s board of directors
451|I|Bylaws: The Company’s Amended and Restated Bylaws
452|I|CAP: “Compensation actually paid,” as defined under Item 402(v) of Regulation S-K
453|I|CC: Compensation Committee of the Board
454|I|CD&A: Compensation Discussion and Analysis
455|I|CEO: Chief Executive Officer
456|I|CFO: Chief Financial Officer
457|I|Charter: The Company’s Restated Certificate of Incorporation
458|I|Control Number: Identification number for each stockholder included in Notice or proxy card
459|I|CS: Corporate Sustainability
460|I|ERM: Enterprise Risk Management
461|I|ESPP: NVIDIA Corporation Amended and Restated 2012 Employee Stock Purchase Plan
462|I|EVP: Executive Vice President
463|I|Exchange Act: Securities Exchange Act of 1934, as amended
464|I|FASB: Financial Accounting Standards Board
465|I|Fiscal 20__: The Company’s fiscal year ended on the last Sunday in January of the stated year
466|I|Form 10-K: The Company’s Annual Report on Form 10-K for Fiscal 2025 filed with the SEC on February 26, 2025
467|I|GAAP: Generally accepted accounting principles in the United States
468|I|Internal Revenue Code: U.S. Internal Revenue Code of 1986, as amended
469|I|Lead Director: Lead independent director
470|I|Meeting: Annual Meeting of Stockholders
471|I|MY PSUs: Multi-year PSUs based on 3-year TSR relative to the S&P 500 with a three-year performance metric, vesting after three years
472|I|Nasdaq: The Nasdaq Stock Market LLC
473|I|NCGC: Nominating and Corporate Governance Committee of the Board
474|I|NEOs: Named Executive Officers consisting of our CEO, our CFO, and our other three most highly compensated executive officers as of the end of Fiscal 2025
475|I|NIM: NVIDIA Inference Microservices
476|I|Non-GAAP Operating Income: GAAP operating income, as the Company reports in its SEC filings, excluding stock-based compensation expense, acquisition-related and other costs, and other. Please see Reconciliation of Non-GAAP Financial Measures in our CD&A for a reconciliation between the non-GAAP financial measures and GAAP results
477|I|Notice: Notice of Internet Availability of Proxy Materials
478|I|NVIDIA, Company, we, us, our: NVIDIA Corporation, a Delaware corporation
479|I|NYSE: New York Stock Exchange
480|I|Proposed Charter: The Company’s proposed Amended and Restated Certificate of Incorporation
481|I|PSU: Performance stock unit
482|I|PwC: PricewaterhouseCoopers LLP
483|I|RBA: Responsible Business Alliance
484|I|RSU: Restricted stock unit
485|I|S&P 500: Standard & Poor’s 500 Composite Index
486|I|SEC: U.S. Securities and Exchange Commission
487|I|Section 162(m): Section 162(m) of the Internal Revenue Code
488|I|Securities Act: Securities Act of 1933, as amended
489|I|Stretch Compensation Plan: Performance goal necessary to earn the maximum award under the Variable Cash Plan and for the maximum numbers of SY PSUs and MY PSUs to become eligible to vest
490|I|SY PSUs: PSUs based on annual Non-GAAP Operating Income performance with a single-year performance metric, vesting over four years
491|I|Threshold: Minimum performance goal necessary to earn an award under the Variable Cash Plan and for SY PSUs and MY PSUs to become eligible to vest
492|I|TSR: Total shareholder return
493|I|Variable Cash Plan: The Company’s variable cash compensation plan
'''),
    'pingan-results-announcement-p001': ('complex-pingan-2024-annual', [1], [(1, 31)], '''
1|P|Hong Kong Exchanges and Clearing Limited~The Stock Exchange of Hong Kong Limited~take no responsibility~no representation~accuracy or completeness~expressly disclaim any liability~whole or any part
3|P|PING AN
5|P|Expertise Creates Value
7|H1|中国平安保险（集团）股份有限公司
9|P|Ping An Insurance (Group) Company of China, Ltd.
11|P|(A joint stock limited company incorporated in the People’s Republic of China with limited liability)
13|P|Stock Code: 2318 (HKD counter) and 82318 (RMB counter)
15|P|(Debt Stock Code: 5131)
17|H2|ANNOUNCEMENT OF AUDITED RESULTS FOR THE YEAR ENDED DECEMBER 31, 2024
19|P|board of directors~Company and its subsidiaries~year ended December 31, 2024~full text of the 2024 Annual Report~Rules Governing the Listing of Securities~preliminary announcements of annual results
21|P|Both the Chinese and English~www.pingan.cn~www.hkexnews.hk~International Financial Reporting Standards~H shareholders~before early April 2025
23|P|By order of the Board
25|P|Ma Mingzhe
27|P|Chairman
29|P|Shenzhen, the PRC, March 19, 2025
31|P|As at the date~executive directors~Ma Mingzhe, Xie Yonglin, Michael Guo, Cai Fangfang and Fu Xin~non-executive directors~Soopakij Chearavanont, Yang Xiaoping, He Jianfeng and Cai Xun~independent non-executive directors~Ng Sing Yip, Chu Yiyun, Liu Hong, Ng Kong Ping Albert, Jin Li and Wang Guangqian
'''),
    'pingan-strategy-cards-p008-011': ('complex-pingan-2024-annual', [8, 9, 10, 11],
        [(275, 283), (285, 317), (319, 342), (344, 370)], '''
275|H2|Corporate Strategy
277|H3|WHAT WE DO
279|P|“pure financial services”~“finance + services”~competition~upgrading of customer needs~insurance~“financial protection”~“insurance + health and senior care services” integrated solutions
281|P|competition~homogeneous offerings~“integrated finance + health and senior care”~service differentiation~financial advisory, family doctor, and senior care concierge
283|C|Corporate Strategy
285|H3|INTEGRATED FINANCE
287|P|customer needs-oriented~technology-enabled financial supermarket~“one customer, multiple accounts, multiple products, and one-stop services.”~“worry-free, time-saving, and money-saving”~customer loyalty~retail customers, contracts per customer and profit per customer~word-of-mouth
289|H4|Exploring customer needs
291|P|personalized, scenario-based, and one-stop~over 240 million retail customers’ data~resource integration~technological innovation~potential customer needs and pain points~wealth management, insurance protection, and consumer finance~home buying, education, senior care~online and offline
293|I|Retention of customers holding 4+ contracts: 98.0%.
294|I|Retail customers: 242 mn.
296|H4|Upgrading the account system
298|P|We build a one-stop financial and daily-life service platform for customers.~integrating accounts in finance, health care, senior care~related daily-life service accounts~all-around, expandable integrated account system~unified, convenient online portal~without the need to switch between multiple platforms or accounts
300|I|“Ping An Jin Guan Jia” app users: ~290 mn.
301|I|“Ping An Pocket Bank” app users: 170 mn+.
302|I|“Ping An Auto Owner” app users: ~236 mn.
304|H4|Building the product matrix
306|P|financial advisory, family doctor and senior care concierge~steady asset appreciation~effective risk management~diverse health and senior care~auto insurance claims, health and senior care, and credit card services~smart, convenient~differential customer experience
308|I|No.1 auto insurance brand: Honored by MIIT for 14 consecutive years.
309|I|Coverage of top 100 and 3A hospitals: 100%.
310|I|Accounts of credit cards in circulation: 46.92 mn+.
312|H4|Providing one-stop services
314|P|“worry-free, time-saving, and money-saving”~integrated account system~finance, health and senior care~AI~big data~online and offline~reduce customer waiting time~asset allocation~loyalty point integration~holistic benefit design~reduce risks and cut costs
316|I|Contracts per customer: 2.92.
317|I|Profit per customer: RMB446.90/person.
319|H3|HEALTH AND SENIOR CARE
321|P|Acting for payers and integrating providers~most cost-effective~professional family doctors and senior care concierges~“worry-free, time-saving, and money-saving”
323|H4|Acting for payers, we build an integrated payment and service platform
325|P|“Healthy China”~payers including insurers and enterprises~retail customers and enterprise employees~over 31 million paying retail customers~nearly 67,000 paying corporate clients~over 29 million employees~over 50%~SOEs~central enterprises~FIEs~bargaining power~resource integration
327|I|Ping An Health’s paying users of strategic business: 31 mn+.
328|I|Large and medium-sized SOEs, central enterprises and FIEs served: 50%+.
330|H4|Integrating providers to build an all-around service system
332|P|convenient, transparent and efficient~setting standards, centralizing procurement, and supervising services~doctors, hospitals, health management institutions, pharmacies~“Nursing, Housing, and Entertainment Alliances.”~35 countries and regions~standardized and cost-effective
334|I|Partner hospitals: 36K+.
335|I|Partner health management institutions: 104K+.
337|H4|The most cost-effective health and senior care services via professional family doctors and senior care concierges
339|P|“online, in-store, in-home and in-company”~Peking University International Hospital~24/7~online-to-offline~domestic and overseas top medical experts~AI concierges, life concierges and doctor concierges~medical care, dining, housing, exercise, wealth, rehabilitation, wellness, entertainment, nursing and hospice
341|I|In-house & external doctors: ~50K.
342|I|Senior care concierge service benefits: Hundreds.
344|H3|TECHNOLOGY ENABLEMENT
346|P|customer needs~“experience-based decision-making”~“data-driven decision-making”~large AI models and big data~five laboratories and nine databases~data-driven business~operations~management~marketing~financial advisers, family doctors and senior care concierges~enhance services, improve efficiency, cut costs and prevent risks
348|H4|Enhance services
350|P|accounts and products~O2O~precisely identifying and meeting customer needs~most suitable~personalized, scenario-based, one-stop
352|I|Data-driven precise diagnosis: 5K+ diseases.
354|H4|Improve efficiency
356|P|AI-enabled~human-AI collaboration~shorten response times~service precision and quality~24/7 online services
358|I|Life policies underwritten within seconds: 93%.
360|H4|Cut costs
362|P|AI replaces and assists humans~cut service costs~financial accounts, products~health and senior care~avoid unnecessary expenditures~precise allocation and recommendation
364|I|Service volume handled by AI: 80%.
366|H4|Prevent risks
368|P|ex ante risk data analysis~AI~credit risk~behavior patterns at source~asset allocation, big data and quantitative models~investment risks~supervises health and senior services~standardizes service quality~service-related risks
370|I|Ping An P&C’s claims savings via smart fraud detection: RMB11.94 bn.
'''),
}

# Each glossary entry is a literal definition, including embedded dates,
# statute identifiers, performance conditions, exclusions and vesting periods.
# Either a complete textual field or one complete ordered definition may own
# it. The declaration is fixed from the source, before compilation; there are
# no quantity equivalences for numbers embedded in these textual definitions.
REVIEW_TYPED_ASSERTIONS = {}
REVIEW_REPRESENTATION_POLICIES = {}
for _row in REVIEW_ASSERTIONS['nvidia-definitions-p017'][3].strip().splitlines()[1:]:
    _line, _role, _definition = _row.split('|', 2)
    _label, _value = _definition.split(': ', 1)
    REVIEW_TYPED_ASSERTIONS[('nvidia-definitions-p017', int(_line))] = [('', _label, _value, {})]
    REVIEW_REPRESENTATION_POLICIES[('nvidia-definitions-p017', int(_line))] = 'either'

# The following callouts are independently printed label/value records. They
# require the existing typed field comparison, including every printed sign,
# approximation marker, currency and suffix. Unsupported mn/K/person forms
# remain complete literal scalar values, never guessed normalized quantities.
for _line, _label, _value in [
    (293, 'Retention of customers holding 4+ contracts', '98.0%.'),
    (294, 'Retail customers', '242 mn.'),
    (300, '“Ping An Jin Guan Jia” app users', '~290 mn.'),
    (301, '“Ping An Pocket Bank” app users', '170 mn+.'),
    (302, '“Ping An Auto Owner” app users', '~236 mn.'),
    (308, 'No.1 auto insurance brand', 'Honored by MIIT for 14 consecutive years.'),
    (309, 'Coverage of top 100 and 3A hospitals', '100%.'),
    (310, 'Accounts of credit cards in circulation', '46.92 mn+.'),
    (316, 'Contracts per customer', '2.92.'),
    (317, 'Profit per customer', 'RMB446.90/person.'),
    (327, 'Ping An Health’s paying users of strategic business', '31 mn+.'),
    (328, 'Large and medium-sized SOEs, central enterprises and FIEs served', '50%+.'),
    (334, 'Partner hospitals', '36K+.'),
    (335, 'Partner health management institutions', '104K+.'),
    (341, 'In-house & external doctors', '~50K.'),
    (342, 'Senior care concierge service benefits', 'Hundreds.'),
    (352, 'Data-driven precise diagnosis', '5K+ diseases.'),
    (358, 'Life policies underwritten within seconds', '93%.'),
    (364, 'Service volume handled by AI', '80%.'),
    (370, 'Ping An P&C’s claims savings via smart fraud detection', 'RMB11.94 bn.'),
]:
    REVIEW_TYPED_ASSERTIONS[('pingan-strategy-cards-p008-011', _line)] = [('', _label, _value, {})]
    REVIEW_REPRESENTATION_POLICIES[('pingan-strategy-cards-p008-011', _line)] = 'typed'

REVIEW_TYPED_ASSERTIONS[('pingan-strategy-cards-p008-011', 298)] = [
    ('We', 'build', 'a one-stop financial and daily-life service platform',
     {'polarity': 'positive', 'tense': 'present'}),
]
REVIEW_REPRESENTATION_POLICIES[('pingan-strategy-cards-p008-011', 298)] = 'mixed'
REVIEW_TYPED_ASSERTIONS[('pingan-results-announcement-p001', 13)] = [
    ('', 'Stock Code', '2318 (HKD counter) and 82318 (RMB counter)', {}),
]
REVIEW_REPRESENTATION_POLICIES[('pingan-results-announcement-p001', 13)] = 'either'

# Printed citation attributions are textual fields with complete literal
# values. They do not assert independently measured quantities or parse the
# cited publications; either complete record form retains that responsibility.
for _sample, _line, _label, _value in [
    ('iea-energy-manufacturing-p037-040', 651, 'Sources', 'IEA analysis based on data from EpochAI (2025a), Papers With Code (2025), and Stanford University (2024).'),
    ('iea-energy-manufacturing-p037-040', 677, 'Source', 'IEA analysis based on data from OMDIA (2025).'),
    ('iea-energy-manufacturing-p037-040', 695, 'Sources', 'IEA analysis based on Garcia Bardon, et al. (2021), Boavizta (2021), and Dell (2019).'),
    ('iea-rise-ai-p021-024', 446, 'Sources', 'IEA analysis based on data from EpochAI (2024), and Coyle and Hampton (2024).'),
    ('iea-rise-ai-p021-024', 460, 'Sources', 'IEA analysis based on data from Bloomberg Terminal (n.d.) and Crunchbase (n.d.).'),
    ('iea-rise-ai-p021-024', 476, 'Source', 'IEA analysis based on data from US Bureau of Economic Analysis (2024).'),
    ('iea-rise-ai-p021-024', 492, 'Source', 'IEA analysis based on data from ITU (n.d.).'),
]:
    REVIEW_TYPED_ASSERTIONS[(_sample, _line)] = [('', _label, _value, {})]
    REVIEW_REPRESENTATION_POLICIES[(_sample, _line)] = 'either'

# These five printed graph identifiers introduce complete nominal definitions,
# not measurements or partially interpreted sentences. Their full literal
# definitions can be retained either as fields or as ordered content. This
# explicit correction to an initially overstrict all-prose strategy follows
# the source's label/definition form, never any candidate representation.
for _line, _label, _value in [
    (1006, 'Graph 7.A', 'Showing option-adjusted spread, the yield spread over a benchmark yield curve adjusted for the value of embedded options.'),
    (1010, 'Graph 7.C', 'Weekly average for federal funds rate futures.'),
    (1018, 'Graph 9.A', 'Net percentage of bank loan officers reporting they are tightening lending standards.'),
    (1020, 'Graph 9.B', 'Net percentage of bank loan officers reporting they are seeing increased loan demand.'),
    (1050, 'Graph 15.B', 'Based on Shanghai interbank offered rate (Shibor) versus secured overnight financing rate (SOFR).'),
]:
    REVIEW_TYPED_ASSERTIONS[('bis-endnotes-technical-annex-p052-057', _line)] = [('', _label, _value, {})]
    REVIEW_REPRESENTATION_POLICIES[('bis-endnotes-technical-annex-p052-057', _line)] = 'either'

REVIEW_CONTROL_ASSERTIONS = {}
REVIEW_ORDERED_SOURCE_GROUPS = {
    'bis-endnotes-technical-annex-p052-057': [(964, 984, 'Endnotes retain their printed citation order and distinct repeated BIS references.')],
    'iea-training-energy-p041-042': [(713, 716, 'Four methodology steps remain ordered and distinct; extrapolation cannot precede fitted-model estimation.')],
    'iea-inference-energy-boxes-p043-048': [
        (736, 741, 'Six independently printed influences on inference energy retain order and attribution.'),
        (807, 809, 'Text, image and video output heuristics remain separate, ordered and bound to their own units.'),
    ],
    'iea-rise-ai-p021-024': [(434, 436, 'Hardware cost, training data and compute drivers remain separate and ordered.')],
}

# These are dependencies on actually executed independent synthetic probes,
# not declarations that a role is supported. The unified runner attaches the
# probe results and refuses source acceptance while any required proof fails.
REVIEW_NUMERIC_ROLE_DEPENDENCIES = {
    'bis-endnotes-technical-annex-p052-057': [
        {'line': 977, 'role': 'bibliographic_year_identifier', 'case_id': 'numeric-role/statute-year'},
        {'line': 988, 'role': 'calendar_period_in_technical_explanation', 'case_id': 'numeric-role/reporting-year'},
    ],
    'iea-energy-manufacturing-p037-040': [
        {'line': 657, 'role': 'calendar_year_in_energy_statement', 'case_id': 'numeric-role/reporting-year'},
        {'line': 695, 'role': 'bibliographic_year_identifier', 'case_id': 'numeric-role/statute-year'},
    ],
    'iea-inference-energy-boxes-p043-048': [
        {'line': 749, 'role': 'calendar_date_in_content', 'case_id': 'numeric-role/calendar-body'},
        {'line': 771, 'role': 'model_version_identifier', 'case_id': 'numeric-role/model-version'},
    ],
    'iea-rise-ai-p021-024': [
        {'line': 450, 'role': 'calendar_period_in_market_statement', 'case_id': 'numeric-role/reporting-year'},
    ],
    'iea-training-energy-p041-042': [
        {'line': 705, 'role': 'model_identifier', 'case_id': 'numeric-role/model-version'},
        {'line': 722, 'role': 'as_of_calendar_date', 'case_id': 'numeric-role/calendar-body'},
    ],
    'nvidia-definitions-p017': [
        {'line': 445, 'role': 'plan_identifier', 'case_id': 'numeric-role/plan-identifier'},
        {'line': 452, 'role': 'legal_citation_identifier', 'case_id': 'numeric-role/statute-reference'},
        {'line': 466, 'role': 'filing_calendar_date', 'case_id': 'numeric-role/calendar-body'},
        {'line': 468, 'role': 'statutory_identity_year', 'case_id': 'numeric-role/statute-year'},
        {'line': 487, 'role': 'typed_literal_citation_identifier', 'case_id': 'numeric-role/typed-text-reference'},
    ],
    'pingan-results-announcement-p001': [
        {'line': 13, 'role': 'securities_and_counter_identifiers', 'case_id': 'numeric-role/security-code-isolated'},
        {'line': 29, 'role': 'signed_calendar_date', 'case_id': 'numeric-role/calendar-attribution'},
    ],
}

SOURCE_REVIEW_NOTES = {
    'bis-endnotes-technical-annex-p052-057': {
        'reviewed_sources': 65,
        'scope': 'All six selections, 21 numbered endnotes and every Graph 2.A through Graph 19.B technical explanation.',
        'responsibility': 'Full explanations own formulas, country lists, periods, caveats, assumptions and graph references; no actual graph data or image semantics.',
        'non_applicability_basis': 'Headings are structural labels; every other selected source is printed text or an ordered endnote, not a table or image.',
        'numeric_role_assertions': [(988, 'Graph 2.A; Q1 2022; Q4 2023; Q1 2000; Q4 2019', 'graph identifiers and calendar periods'),
                                    (1008, 'June 2021–June 2024', 'calendar period, not measured quantity')],
        'declaration_correction': 'Five complete nominal graph definitions were initially classified too strictly as content only; specified field/content alternatives now preserve their entire label and definition without inventing quantities.',
    },
    'iea-energy-manufacturing-p037-040': {
        'reviewed_sources': 31,
        'scope': 'All five selections, benchmark caveats, electricity concentration, hardware energy and emissions, four figure titles/captions and notes.',
        'responsibility': '1.5%, 10–25/100 MW, 100000 households, manufacturing/operation comparison, regional and emissions shares retain their complete printed clauses and restrictions.',
        'non_applicability_basis': 'Figure assets themselves are outside semantic scope; their titles, captions, notes, sources and associated textual claims remain applicable.',
        'numeric_role_assertions': [(657, '2024', 'calendar year'), (695, 'Garcia Bardon, et al. (2021)', 'bibliographic identity')],
        'declaration_correction': 'Printed Source/Sources attributions explicitly allow one full literal field or complete content; these are references, not measured financial fields.',
    },
    'iea-inference-energy-boxes-p043-048': {
        'reviewed_sources': 44,
        'scope': 'All nine selections, six inference influences, both boxes, three figure notes, footnotes 5–8, experimental caveats and 100 TWh heuristics.',
        'responsibility': 'Complete clauses retain model identities, query/task versus generation distinctions, selected GPU-only measurement scope, energy units, hedges, rebound and implementation caveats.',
        'source_ambiguity': 'L789 literally says increasing per-token energy consumption; retain that authorized text despite neighboring lower-per-task statements, do not correct it from external knowledge.',
        'non_applicability_basis': 'No chart interpretation; only authorized titles, captions, claims, notes and cited source text.',
        'numeric_role_assertions': [(749, '20 January 2025', 'calendar date'),
                                    (771, 'Yi-1.5 9B; Llama 3.3; SD-XL 1.0-base; CogVideoX-5b', 'model/version identifiers')],
        'declaration_correction': 'L785 transcription preserves source uppercase Larger; no production semantic expectation changed.',
    },
    'iea-rise-ai-p021-024': {
        'reviewed_sources': 33,
        'scope': 'All six selections from rise-of-AI drivers through financial expectations, the historical ICT box and household/business connectivity.',
        'responsibility': 'Full content retains comparison baselines, 65% statement alongside USD16/12trillion, planned 2025 capex, historical analogy, investment uncertainty and connectivity denominators.',
        'non_applicability_basis': 'Only figure textual elements apply; charts themselves are uninspected and make no semantic claims.',
        'numeric_role_assertions': [(450, 'S&P 500; November 2022; end of 2024', 'index identifier and calendar periods'),
                                    (446, 'EpochAI (2024)', 'bibliographic identity')],
        'declaration_correction': 'Complete literal Source/Sources records allow field/content alternatives; this does not interpret citation years as measured quantities.',
    },
    'iea-training-energy-p041-042': {
        'reviewed_sources': 16,
        'scope': 'All four selections including full paragraphs, four methodology bullets, three footnotes and Figure1.15 text; not just old L730.',
        'responsibility': 'GPT4 data/compute, rated-power versus use, 84% load factor, fine-tuning comparison, model extrapolation, 1700GWh/1.7TWh and both electricity denominators retain their source and order.',
        'non_applicability_basis': 'Figure asset not inspected; its textual caption and claims remain required. Never hitting maximum designed power is a textual footnote, not N/A.',
        'numeric_role_assertions': [(705, 'GPT-4', 'model identifier'), (722, '24 March 2025', 'calendar date'),
                                    (714, '84%; 154 MW; 310 GWh', 'printed quantities remain distinct from those identifiers')],
    },
    'nvidia-definitions-p017': {
        'reviewed_sources': 50,
        'scope': 'DEFINITIONS heading and all49 printed glossary entries.',
        'responsibility': 'Each complete literal label/definition pair preserves identity, eligibility, time, assumptions, exclusions and internal references. Source strategy permits either full field or full content with identical ownership.',
        'numeric_roles': '2007Plan, ASC718, Item402(v), Form10K, Section162(m), Fiscal20__, Acts1933/1934 and Code1986 are textual roles, not interchangeable quantities.',
        'non_applicability_basis': 'No images or tables selected; heading has structural responsibility, definitions have full applicable content/field responsibility.',
        'numeric_role_assertions': [(445, '2007 Plan', 'plan identifier'), (452, 'Item 402(v)', 'legal citation'),
                                    (461, '2012 Employee Stock Purchase Plan', 'plan identity'), (466, 'February 26, 2025', 'calendar date')],
    },
    'pingan-results-announcement-p001': {
        'reviewed_sources': 16,
        'scope': 'Full announcement page including liability disclaimer, company identities, stock/debt codes, audited reporting period, languages and distribution timing, authorization/signature and complete categorized board list.',
        'responsibility': '2318HKD and82318RMB are distinct counter identities, 5131 debt identifier stays separate; dates are literal calendar/distribution terms, not numeric quantities.',
        'non_applicability_basis': 'Logo words are selected textual content; no unselected logo imagery or inferred signature relation is added.',
        'numeric_role_assertions': [(13, '2318 (HKD counter) and 82318 (RMB counter)', 'distinct securities and counter identities'),
                                    (15, '5131', 'debt identifier'), (29, 'March 19, 2025', 'calendar date')],
        'declaration_correction': 'The combined two-counter stock declaration permits its complete typed property or complete content with the same two distinct counter bindings, rather than demanding a newly decomposed identifier schema.',
    },
    'pingan-strategy-cards-p008-011': {
        'reviewed_sources': 53,
        'scope': 'All four selections and four strategy sections with every subheading, narrative, callout and the textual strategy caption.',
        'responsibility': 'Complete narrative reasoning plus independently labeled callouts: retail/customer/account/medical coverage/service/technology measures; first L298 proposition remains protected typed responsibility with surrounding content separately owned.',
        'non_applicability_basis': 'Caption only, no interpretation of the strategy image. Each printed metric remains applicable, no zero-item scoring assumption.',
        'numeric_role_assertions': [(339, '24/7', 'service schedule'), (293, '98.0%', 'retention quantity')],
        'declaration_correction': 'L281/L306 anchors remove an incorrectly transcribed closing quote before the printed comma; the authorized wording remains unchanged.',
    },
}
