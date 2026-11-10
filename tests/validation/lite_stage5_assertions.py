"""Independent source declarations for the fixed two literal-label samples.

Written from authorized source text before the new production compilation.
Complete paragraphs retain all numbers, qualifications and ordering. They do
not certify unrestricted language interpretation or interpret linked images.
"""

IEA = 'iea-data-centre-definitions-history-p049-061'
PINGAN = 'pingan-integrated-finance-p021'

REVIEW_ASSERTIONS = {
 IEA: ('complex-iea-energy-ai-2025', list(range(49, 62)), [
  (813,825),(827,843),(845,845),(847,860),(861,873),(874,889),
  (890,904),(906,906),(908,918),(920,920),(922,936),(938,952),
  (954,964),(966,966),(968,976),(978,992),(994,1006)], '''
813|H2|Chapter 2. Energy for AI
815|P|The evolution of energy demand and how to meet it
817|H3|SUMMARY
819|I|model training and deployment~mainly in data centres~415 terawatt hours (TWh)~1.5%~2024~12% per year~last five years
820|I|Base Case~server shipments~Lift-Off, High Efficiency and Headwinds~hardware and software~AI uptake~bottlenecks
821|I|Base Case~945 TWh~2030~more than doubling~2024~United States~China and Europe~less than 10%
822|I|Lift-Off~over 1 260 TWh~2030~High Efficiency~800 TWh~Headwinds~670 TWh~2035~700 TWh to 1 720 TWh~four cases
823|I|Natural gas~175 TWh~2035~Base Case~United States~Lift-Off~290 TWh~Renewables~450 TWh~Nuclear power
824|I|Grid congestion~transformers and gas turbines~around 20%~additions by 2030~Base Case~risk of delay
825|I|Avoiding this risk~energy and technology~Permitting times~Grid operators~power and grid availability~operational flexibility~better data
827|H3|2.1 Introduction
829|P|Investment~nearly 70%~last two years~artificial intelligence~digitalisation~timely, secure and sustainable
831|P|relatively new actors~remain limited~substantial uncertainty~heterogeneous~see Chapter 1~challenging
833|P|electricity supply~emerging market and developing economies~cooling~Advanced economies~two decades~permitting times~supply chains
835|P|This chapter explores these issues across the following sections:
837|I|Section 2.2~determinants~consume today
838|I|Section 2.3~International Energy Agency (IEA)~outlook
839|I|Section 2.4~information and communication technology (ICT)~beyond data centres
840|I|Section 2.5~electricity supply scenarios~demand growth
841|I|Section 2.6~interact with grids~risk of project delays
843|H4|2.1.1 Case design
845|P|uncertainty~scenario-based approach~two to three years~longer lead times~high upfront investment~three to five years~AI uptake
847|P|two timeframes~Section 2.3.1~2030~Base Case~Section 2.3.2~2035~four cases~2.3.1 and 2.3.2
849|I|Base Case~current regulatory conditions~server shipments to 2028~after 2028~Efficiency improvements~despite increasing demand
850|I|Lift-Off Case~stronger growth~more resilient supply chain~location, powering and operations~faster
851|I|High Efficiency Case~similar constraints~stronger progress~same level of demand~reduced electricity
852|I|Headwinds Case~downside~slower than expected AI adoption~local bottlenecks~delays~most ambitious
854|P|novelty~definitions~Readers more familiar~skip~section 2.2.1~historical trends
856|H4|2.1.2 Key definitions and concepts
858|P|several types~following categorisations:
860|I|Enterprise~own use~smaller and less efficient~28%~today~85% in 2005
861|I|Colocation and service provider~lease space~colocation~service providers~hundreds or thousands~36%~today
862|I|Hyperscale~Amazon Web Services, Google, Meta and Microsoft~efficient~10%~2010~37% today
864|H4|Figure 2.1. Data centre components
866|C|Figure 2.1
868|P|Effective design and integration~continuous operation~optimal performance
870|P|servers, storage systems, networking equipment~racks~rows~Figure 2.1~IT~auxiliary equipment~following:
872|I|Servers~process and store~CPUs~GPUs~60%~varies greatly~Figure 2.2
873|I|Storage systems~centralised~backup~5%~electricity consumption
874|I|Networking equipment~switches~routers~load balancers~up to 5%
875|I|Cooling and environmental controls~temperature and humidity~7%~hyperscale~over 30%~enterprise
876|I|Uninterruptible power supply batteries~backup power generators~outages~rarely used~necessary~reliability
877|I|Other infrastructure~lighting and office equipment~onsite staff
879|P|components~varies greatly by data centre type~nature and efficiency~Figure 2.2~today
881|H4|Figure 2.2. Share of electricity consumption by data centre and equipment type, 2024
883|C|Figure 2.2
885|P|Hyperscale~most efficient~servers and other IT equipment
887|P|Several technical characteristics~electricity consumption:
889|I|Installed IT capacity~megawatts (MW)~Total installed capacity~auxiliary equipment~partially filled~Maximum designed capacity~smaller than
890|I|utilisation rate~actively being used~below 20%~hyperscale~up to 50%
891|I|Idle power~background operations~not actively processing~percentage~60% in 2010~35%~modern servers
892|I|Power usage effectiveness (PUE)~ratio~total consumption/IT consumption~cooling and lighting~around 2~1 kilowatt hour [kWh]~every 1 kWh~just under 1.15~0.15 kWh
894|P|several kinds of chips~server architectures:
896|I|Central processing units (CPUs)~primary components~instructions~operations
897|I|Graphics processing units (GPUs)~tensor processing units~parallel computations~faster
898|I|Accelerated servers~GPUs or similar accelerator chips~specific tasks~AI training and deployment
900|H3|2.2 Electricity consumption of data centres
902|H4|2.2.1 Historical electricity consumption of data centres
904|H5|A sharp acceleration in recent years
906|P|Internet revolution~1990s~United States~2000 and 2005~Koomey, 2007~2007-2008~decoupling~migration~declining idle power
908|H4|Figure 2.3. Total data centre electricity consumption by equipment type and data centre type, 2005-2024
910|C|Figure 2.3
912|P|decade of limited growth~accelerate again after 2015
914|P|Note: GW = gigawatt; TWh = terawatt hour.
916|P|Sources: IEA analysis~IDC (2024a)~OMDIA (2025)~SemiAnalysis (2025)
918|P|around 2017~cloud computing~online media~social media~AI~2015 and 2024~four times faster~per-task basis~outstripped
920|P|Figure 2.4~2005 to 2015~2015 to 2023~more than 25% per year~4%~8%~3% annually~10%~2024
922|H4|Figure 2.4. Average annual change in key drivers of data centre electricity consumption globally, 2005-2015 and 2015-2023
924|C|Figure 2.4
926|P|Robust service demand growth~acceleration~slowdown~faster electricity consumption growth
928|P|* Data starts in 2007.~** Data ends in 2022, estimated for 2022.
930|P|Sources: IEA analysis~Cisco (2008)~Cisco (2015)~Cisco (2019)~ITU (2025)~Meltwater (2024)~SPEC (2024)~World Bank (2024a)
932|H4|Box 2.1. What share of data centre electricity demand comes from AI?
934|P|challenging question~only one of the workloads~no comprehensive data~limited visibility~traditional AI~very wide~Figure 2.5
936|P|second-best approach~accelerated servers~proxy~24%~15%~2024
938|H5|Figure 2.5. Estimated data centre electricity demand due to AI, 2020-2030
940|C|Figure 2.5
942|P|vary widely~at best~imperfect proxies
944|P|Sources: IEA analysis~Deloitte (2024)~Gartner (2024)~Goldman Sachs (2024)~Schneider Electric (2024)~SemiAnalysis (2024)~Shehabi, et al., (2024)
946|P|imperfect proxy~training~conventional servers~non-AI related~scientific computing~end-user devices~section 2.4~uncertainty
948|H5|Data centre electricity consumption is not spread evenly around the world
950|P|United States, Europe and China~85%~12% a year~2015 and 2024~180 TWh~45%~more than 4%~Figure 2.6
952|P|China~2015 onwards~15% per year~more than twice~2005 and 2015~7%~100 TWh~electric vehicles~25%~less than 20%~data gaps~IEA, 2025
954|H4|Figure 2.6. Electricity consumption of data centres by region, 2005-2024
956|C|Figure 2.6
958|P|acceleration~2017~United States~lesser extent~China
960|P|Europe~less than 2%~China’s (1.1%)~70 TWh in 2024~15%~Japan~less than 20 TWh~2%~India~9 TWh~Box 2.2~0.5%~rapid growth
962|H4|Box 2.2. Country focus: India
964|P|India~USD 200 billion~2024~USD 220 billion~950 million~June 2024~2 GW~6.5 million Indian households~four years~over 2 GW~next two years~nearly 5 GW by 2030
966|P|IndiaAI Mission~USD 1.2 billion~over 18 000 GPUs~start-ups and research~Uttar Pradesh~100% exemption~ten years~new data centres
968|P|India~Coal fuels 74%~beyond 2030~open access~PPAs~renewable~Bharti Airtel~140 GWh~annually~captive solar~wind
970|P|India~grid reliability~backup and captive power~power supply interruptions~upgrades~solar PV and wind~battery storage~transmission
972|H5|Figure 2.7. India’s total data centre capacity and electricity generation mix, 2020-2030
974|C|Figure 2.7
976|P|India~double by 2030~coal dominates~renewables increases to 35%
978|H5|Data centre electricity consumption from a broader perspective
980|P|around 4%~2014 and 2024~appliance adoption~industrial electrification~250 TWh~Spain~700 TWh~Figure 2.8
982|H4|Figure 2.8. Increase in electricity demand by sector in the Base Case, 2014-2024
984|C|Figure 2.8
986|P|Over the past decade~almost as much as for transport
988|H5|All historical data are estimates, not measurements
990|P|very few governments~Chapter 5~estimates~challenges and gaps~lack of common definitions~Masanet, Lei and Koomey, 2024~widely divergent~historical
992|P|companies and institutions~not use a consistent scope~maximum designed capacity~actual installed IT capacity~not filled~progressively~expensive third-party~not available
994|P|outdated or overly simplistic PUE~lack of high-quality~utilisation rates~idle server power~workloads and hardware~discrepancies
996|P|rapid adoption of GPUs~limited available data~annual shipments~installed stock~more power intensive~hyperscale and colocation~do not report~specifically
998|P|all historical data~modelled estimates, not measured data~range~wide~Figure 2.9~Triangulating~converging~Kamiya and Coroamă, 2025a~intensive~annex
1000|H4|Figure 2.9. Comparison of three approaches to estimating global data centre electricity consumption, 2023
1002|C|Figure 2.9
1004|P|Different modelling approaches can lead to a wide range of estimates
1006|P|Source: IEA analysis~Kamiya and Coroamă (2025a)
'''),
 PINGAN: ('complex-pingan-2024-annual', [21], [(616,634)], '''
616|H2|Integrated Finance
618|C|Photograph
620|H3|THE INTEGRATED FINANCE STRATEGY
622|P|retail customers (1)~customer needs-oriented~account system~one customer, multiple accounts, multiple products, and one-stop services~worry-free, time-saving, and money-saving~contracts per customer and profit per customer~word-of-mouth
624|P|Note: (1) Retail customers refer to retail customers holding valid financial products with the Group’s core financial companies.
626|H3|Ping An’s Unique Advantages in Integrated Finance
628|H4|An integrated financial services group with a full suite of financial licenses, extensive presence and strong synergies
630|P|full suite of financial licenses~robust shareholding~Chinese market leaders~acquisition, activation, migration and retention~reduce operational and risk costs
632|H4|An industry leader focusing on Chinese markets and core financial businesses
634|P|Chinese mainland~Ping An Life~second largest life insurer~premium income~Ping An P&C~second largest property and casualty insurer~Ping An Asset Management~second largest insurance asset manager~AUM~Ping An Bank~assets, net profit
'''),
}

# The final, fully supported modal statement must remain typed. Other
# multi-clause paragraphs are predeclared complete content, without overlap.
REVIEW_TYPED_ASSERTIONS = {
 (IEA, 1004): [('Different modelling approaches', 'lead',
  'lead to a wide range of estimates', {'modality': 'can', 'polarity': 'positive'})],
}
REVIEW_SOURCE_OVERRIDES = {(IEA, 1004): {'representation': 'typed'}}

# Non-T carrier syntax is finite and independently located. All other
# non-whitespace original characters must have exactly one literal owner.
LITERAL_CONTROL_POSITIONS = {
 IEA: {914: {4: ':', 19: ';', 25: '='}, 916: {7: ':'},
       930: {7: ':'}, 944: {7: ':'}, 1006: {6: ':'}},
 PINGAN: {624: {4: ':'}},
}
REVIEW_RESPONSIBILITY_NOTES = {
 IEA: 'All 110 sources: scenarios remain scenarios, proxies and estimates remain qualified; figures supply captions/references only. Retain every printed period, unit, threshold and citation in complete ordered content. L1004 retains one typed modal proposition. Note, GW and TWh retain original literal occurrences.',
 PINGAN: 'All ten sources: strategy remains strategy; retail customer definition stays attached to (1), heading scope and order. Distinct company rankings and premium/AUM bases remain in complete content. Photograph caption is preserved without image interpretation.',
}


def check_literal_source(graph, original, target):
    """Independent, occurrence-based partition over original local spans.

    No production text projector, audit helper or candidate supplies the
    answer. The finite field delimiter policy above is authored in advance.
    """
    sample_id = original['sample_id']
    source = target['reference']
    raw = target.get('raw_text', target['text'])
    line = source['lines'][0]
    pieces = []
    for node in graph['nodes']:
        if node['id'] not in graph['projections']['T']:
            continue
        origins = node.get('source_fragments', [node['source']])
        literals = node.get('source_fragment_texts', [node['text']])
        assert len(origins) == len(literals)
        cursor = 0
        for origin, literal in zip(origins, literals, strict=True):
            # Each joined fragment must really occur in order in this atom;
            # inserted join whitespace never owns an original character.
            part = literal.strip()
            start = node['text'].find(part, cursor)
            assert start >= cursor, (sample_id, line, 'joined literal order')
            assert not node['text'][cursor:start].strip(), (sample_id, line, 'unmapped inserted literal')
            cursor = start + len(part)
            if origin.get('path') != source['path'] or origin.get('lines') != source['lines']:
                continue
            assert not any(origin.get(k) for k in ('cell', 'native_path', 'block', 'block_lines'))
            a, b = origin.get('text_span', [0, len(raw)])
            assert 0 <= a < b <= len(raw) and raw[a:b].strip() == part, (
                sample_id, line, 'literal source mismatch', origin, literal)
            pieces.append({'span': [a, b], 'requirement_id': node['id'], 'text': raw[a:b]})
        assert not node['text'][cursor:].strip(), (sample_id, line, 'unmapped literal tail')
    pieces.sort(key=lambda piece: piece['span'])
    assert pieces, (sample_id, line, 'no literal responsibility')
    controls = []
    for pos, char in enumerate(raw):
        owners = [p for p in pieces if p['span'][0] <= pos < p['span'][1]]
        syntax = LITERAL_CONTROL_POSITIONS[sample_id].get(line, {}).get(pos) == char
        assert len(owners) <= 1, (sample_id, line, 'duplicate literal responsibility', pos, owners)
        if not char.isspace() and not syntax:
            assert len(owners) == 1, (sample_id, line, 'missing literal responsibility', pos, char)
        if syntax and not owners:
            controls.append({'span': [pos, pos + 1], 'text': char,
                             'basis': 'independently_declared_field_delimiter'})
    return {'literal_pieces': pieces, 'non_T_syntax': controls,
            'original_source': source, 'no_duplicate_or_missing_literal_occurrences': True}
