import re

s1 = "allow group abc to manage foo in compartment abc"
s2 = "Allow group abc to manage foo in compartment abc"
s3 = "Allow group abc,def to manage foo in compartment abc"
s4 = 'Allow group abc to manage foo in compartment abc where ALL {instance.id=\'fdfd\'}'
s5 = "Allow group abc,def {} foo in compartment abc"
s6 = ' ALLOW group sddsfs,l { SUBNET_READ, SUBNET_ATTACH } in compartment a where all {dssds,sdsds}'
s7 = "Allow dynamic-group abc,def to manage some-stuff in tenancy"

statements = [s1,s2,s3,s4,s5,s6,s7]

regex = r'^\s?allow\s(?P<subjecttype>service|any-user|any-group|dynamic-group|group)\s+(?P<subject>([\w\/\'.,+-]|,\s)+)?\s*(to\s+)?((?P<verb>read|inspect|use|manage)\s+(?P<resource>[\w-]+)|(?P<perm>[\s{},\w]+))\s+in\s+(?P<locationtype>tenancy|compartment id|compartment)\s*(?P<location>[\w\':.-]+)?(?:\s+where\s(?P<condition>.+))?(?:\s(?P<optional>.+))?$'
for s in statements:
    #result = re.search(r'^allow\s(?P<subject>\w,+)\sto\s(?P<verb>\w+)\s(?P<resource>\w+)\sin\s(?P<location>\w+)(?:\swhere\s(?P<condition>\w+))', s.casefold())
    #result = re.search(r'^allow (?P<subject>.+to(?P<verb>.+)\s(?P<resource>.+)\sin\s(?P<location>.+)$', s.casefold())
    #result = re.search(r'^\ballow\sgroup\s(?P<subject>[\w,]+)\sto\s(?P<verb>\w+)\s(?P<resource>\w+)\sin\s(?P<locationtype>tenancy|compartment\s|compartment\sid\s)(?P<location>\w+)?(?:\swhere\s(?P<condition>.+))?$', s.casefold())
    # Use Special Regex String with ignore case
    result = re.search(regex,s,re.IGNORECASE)
    print(f"Statement (type): {s} Match: {result} ({result.group('subjecttype')})")
    print(f"-subject: {result.group('subject')} type: {result.group('subjecttype')}")
    if result.group('perm') is not None:
        print(f"-perm: {result.group('perm')}")
    else:
        print(f"-verb / resource: {result.group('verb')} / {result.group('resource')}")
    print(f"-location (type): {result.group('location')} ({result.group('locationtype')})")
    print(f"-condition: {result.group('condition')}")
    print(f"---{result.groups()}---")

s8 = "allow dynamic-group
  'inst-Domain'/'inst-art-app-dg', 'inst-Domain'/'inst-dataflow-runs-dg', 'inst-Domain'/'inst-dataflow-runs-base-dg',
  'inst-Domain'/'inst-dataflow-runs-collect-dg', 'inst-Domain'/'inst-dataflow-runs-label-dg',
  'inst-Domain'/'inst-dataflow-runs-transform-dg', 'inst-Domain'/'inst-mdi-instance-dg'
to manage all-resources in healthscidev1 where all {
  request.permission not in (
    /BYOIP_RANGE_*/, /DNS_RESOLVER_*/, /CPE_*/, /CROSS_CONNECT_*/, /DRG_*/, /IPSEC_*/, /INTERNET_GATEWAY_*/, /IPV6_*/,
    /LOCAL_PEERING_GATEWAY*/, /NAT_GATEWAY_*/, /REMOTE_PEERING_CONNECTION_*/, /ROUTE_TABLE_*/, /SECURITY_LIST_*/,
    /SERVICE_GATEWAY_*/, /VCN_*/, /VIRTUAL_CIRCUIT_*/, /VLAN_*/, /*_VTAP_*/, /VTAP_*/, /NETWORK_FIREWALL_POLICY_*/,
    /SUBNET_*/, /BASTION_*/, 'AUTHENTICATION_POLICY_UPDATE', /CREDENTIAL_*/, /IDENTITY_PROVIDER_*/, /POLICY_*/,
    'TAG_NAMESPACE_MOVE', 'TENANCY_UPDATE', /NETWORK_SOURCE_*/, /DOMAIN_*/
  ),
  any {
    all {
      request.groups.id = target.resource.compartment.tag.g1.id,
      any { target.resource.compartment.tag.g1.tbn != /*/, target.resource.compartment.tag.g1.tbn = target.bucket.name },
      request.permission in (
        target.resource.compartment.tag.g1.p1, target.resource.compartment.tag.g1.p2,
        target.resource.compartment.tag.g1.p3, target.resource.compartment.tag.g1.p4,
        target.resource.compartment.tag.g1.p5, target.resource.compartment.tag.g1.p6,
        target.resource.compartment.tag.g1.p7, target.resource.compartment.tag.g1.p8,
        target.resource.compartment.tag.g1.p9, target.resource.compartment.tag.g1.p10
      )
    },
    all {
      request.groups.id = target.resource.compartment.tag.g2.id,
      any { target.resource.compartment.tag.g2.tbn != /*/, target.resource.compartment.tag.g2.tbn = target.bucket.name },
      request.permission in (
        target.resource.compartment.tag.g2.p1, target.resource.compartment.tag.g2.p2,
        target.resource.compartment.tag.g2.p3, target.resource.compartment.tag.g2.p4,
        target.resource.compartment.tag.g2.p5, target.resource.compartment.tag.g2.p6,
        target.resource.compartment.tag.g2.p7, target.resource.compartment.tag.g2.p8,
        target.resource.compartment.tag.g2.p9, target.resource.compartment.tag.g2.p10
      )
    },
    all {
      request.groups.id = target.resource.compartment.tag.g3.id,
      any { target.resource.compartment.tag.g3.tbn != /*/, target.resource.compartment.tag.g3.tbn = target.bucket.name },
      request.permission in (
        target.resource.compartment.tag.g3.p1, target.resource.compartment.tag.g3.p2,
        target.resource.compartment.tag.g3.p3, target.resource.compartment.tag.g3.p4,
        target.resource.compartment.tag.g3.p5, target.resource.compartment.tag.g3.p6,
        target.resource.compartment.tag.g3.p7, target.resource.compartment.tag.g3.p8,
        target.resource.compartment.tag.g3.p9, target.resource.compartment.tag.g3.p10
      )
    },
    all {
      request.groups.id = target.resource.compartment.tag.g4.id,
      any { target.resource.compartment.tag.g4.tbn != /*/, target.resource.compartment.tag.g4.tbn = target.bucket.name },
      request.permission in (
        target.resource.compartment.tag.g4.p1, target.resource.compartment.tag.g4.p2,
        target.resource.compartment.tag.g4.p3, target.resource.compartment.tag.g4.p4,
        target.resource.compartment.tag.g4.p5, target.resource.compartment.tag.g4.p6,
        target.resource.compartment.tag.g4.p7, target.resource.compartment.tag.g4.p8,
        target.resource.compartment.tag.g4.p9, target.resource.compartment.tag.g4.p10
      )
    }
  }
}"