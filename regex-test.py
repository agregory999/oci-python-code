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
