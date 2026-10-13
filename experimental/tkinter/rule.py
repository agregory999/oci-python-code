# Rule Interpretation with parser
# get all tokens any | all | { | } | , | condition
# parse and recurse with anything inside { xxx }
# for each recursion step, re-parse

import re

# Constant

REGEX_TOKENIZE = r'\s*(any|all|,|{|}|[\w\'\.\s=]+)'
REGEX_TOKENIZE3 = r'\s*(any|all|,|{|}|(?P<inner>[\w\'\.\,\s=]+))'
REGEX_TOKENIZE2 = r'\s*(?P<begin>any|all|{\s*(?P<inner>.*)\s*})'
REGEX_COMPONENT = r'(?P<condition>([\w\.]+\s+=\s+[\w\.\']+))'
REGEX_COMPONENT_START = r'^(?P<condition>([\w\.]+\s+=\s+[\w\.\']+))'
REGEX_INNER = r'{(?P<inner>.*)}'
REGEX_CONDITION = r'\s*(?P<subject>[\w\.]+)\s*=\s*(?P<predicate>[\w\.\']+)\s*'

ANY = "ANY"
ALL = "ALL"

# Classes
class Condition:
    subject = ""
    predicate = ""

    def __init__(self, condition: str, level: int):
        self.condition = condition
        self.level = level

        results = re.search(REGEX_CONDITION, condition, re.IGNORECASE|re.MULTILINE)
        if results:
            self.subject = results.group('subject')
            self.predicate = results.group('predicate')
            print(f'{"  "*self.level}Subject: {self.subject} = Condition: {self.predicate}')



class Rule:

    # Rule may be "any", "all", or another rule
    rules = []

    def __init__(self, matching_rule: str, level: int):
        self.matching_rule = matching_rule
        self.level = level
        self.parse()

    def parse(self):

        # conditions = re.search(REGEX_COMPONENT_START, self.matching_rule, re.IGNORECASE|re.MULTILINE)

        # if conditions:
        #     print(f'{"  "*self.level}Initial Cond: {conditions.groups()}')

        # Tokenize, then for each token do something
        # tokens = re.search(REGEX_TOKENIZE2, self.matching_rule, re.IGNORECASE|re.MULTILINE)
        tokens = re.findall(REGEX_TOKENIZE3, self.matching_rule, re.IGNORECASE|re.MULTILINE)
        inner = re.search(REGEX_TOKENIZE3, self.matching_rule, re.IGNORECASE|re.MULTILINE)

        # Process tokens
        for t in tokens:
            print(f'{"  "*self.level}Token: {t}')

            if t[0].casefold() == "any":
                self.rules.append(ANY)
            elif t[0].casefold() == ",":
                pass
            elif t[0].casefold() == "all":
                self.rules.append(ALL)
            elif t[0].casefold() == "{":    
                # Recurse with re-parsed insides of { }
                if inner:
                    inner_text = inner.group('inner')
                    print(f"{"  "*self.level}t: {inner_text}")
                    print(f"{"  "*self.level}Recursing")
                    self.rules.append(Rule(inner_text, self.level+1))
            elif t[0].casefold() == "}":
                # Fall back case
                print(f"{"  "*self.level}Fall Back")
                pass
            else:
                # Now deal with inner
                try:
                    # inner = tokens.group('inner')
                    # inner = t[0]
                    print(f'{"  "*self.level}Deal with: {t[0]}')
                    # self.rules.append(Rule(inner,self.level+1))
                except Exception as e:
                    print(f'{"  "*self.level}Error: {e}')


            # elif t == "{":
            #     pass
            #     # # Ignore the bracket and try to initialize the rest 
            #     # # Get the inner part
            #     # print(f'{"  "*self.level}Current Matching Rule: {self.matching_rule}')
            #     # print(f'{"  "*self.level}Current Matching Rule: {self.matching_rule}')

            #     inner = re.search(REGEX_INNER, self.matching_rule, re.IGNORECASE|re.MULTILINE)
            #     if inner:
            #         print(f'{"  "*self.level}Inner: {inner.group('inner')}')
            #     # #     print(f'{"  "*self.level}->Recursion')
            #         self.rules.append(Rule(inner.group('inner'), self.level+1))
            #     # # else:
            #     # #     print(f'{"  "*self.level}No Match')
            # elif t == "}":
            #     # This is the fallback case
            #     pass
            # elif t == ",":
            #     # This is the fallback case
            #     pass
            # else:
            #     print(f'{"  "*self.level}Token to deal with: {t}')
            #     # # See if token is a list of them
            #     # conditions = re.findall(REGEX_COMPONENT, t, re.IGNORECASE|re.MULTILINE)
            #     # if conditions:
            #     #     print(f'{"  "*self.level}Condition count: {len(conditions)}')
            #     #     for i,c in enumerate(conditions):
            #     #         print(f'{"  "*self.level}Condition{i}: {c}')
            #     #         self.rules.append(Condition(c, self.level))

            #     # # See if token is a complete condition, or list of them
            #     conditions = re.search(REGEX_COMPONENT_START, t, re.IGNORECASE|re.MULTILINE)
            #     if conditions:
            #         m = conditions.group('condition')
            #         print(f'{"  "*self.level}Condition1: {m}')
            #         self.rules.append(Condition(m, self.level))
                

        # List of rules, or ANY|ALL

    def print():
        # Print something
        pass

def pprint(input: str, level = 0):
    for i,c in enumerate(input):
        if c == '{':
            pprint(input[i+1:], level+1)
        else:
            print(f'{c}', end="")


if __name__ == "__main__":
    dg_rule = "ALL {instance.compartment.id = 'ocid1.compartment.oc1..aaaaaaaa3u5rnknkvw73mfvmw6e7ewf7k6gjnrn5id53qzeq6k6zcm24hqfq',instance.id = 'ocid1.compartment.oc1..aaaaaaaa3u5rnknkvw73mfvmw6e7ewf7k43jnrn5id53qzeq6k6zcm24hqfq'}"

    dg_rule2 = "All {instance.compartment.id='ocid1.compartment.oc1.phx.oc1.phx.samplecompartmentocid6q6igvfauxmima74jv',tag.department.operations.value='45'}"

    dg_rule3 = "any {ALL {resource.type = 'fnfunc', resource.compartment.id = 'ocid1.compartment.oc1..aaaaaaaaqlfgrgl64hzenezffdwm65zjllopuprhamz7z5m4jg465qdlze7q'},All {resource.compartment.id = 'ocid1.compartment.oc1..aaaaaaaaqlfgrgl64hzenezffdwm65zjllopuprhamz7z5m4jg465qdlze7q', Any {resource.type = 'devopsdeploypipeline', resource.type = 'devopsbuildpipeline', resource.type = 'devopsrepository', resource.type = 'devopsconnection', resource.type = 'devopstrigger'} } }"
    # print(f"Rule: {dg_rule}")
    # rule = Rule(dg_rule, 0)
    # print("----")
    # print(f"Rule2: {dg_rule2}")
    # rule = Rule(dg_rule2, 0)
    # print("----")
    # print(f"Rule3: {dg_rule3}")
    # rule = Rule(dg_rule3, 0)
    # rule.parse()

    pprint(dg_rule3)