

############################
# Main
############################

# def recparse(rule:str, level:int):
#     need_recurse_pattern = r"^\s*(?P<oper>ANY|ALL)\s*{(?P<rest>.*)}\s*$"
#     inner_pattern = r"^\s*(?P<oper>ANY|ALL)?\s*{?(?P<condition>[\w'\s.]+=[\s\w'.]+)|(\s*,?\s*)}?\s*$"

#     result = re.search(need_recurse_pattern, rule, re.IGNORECASE | re.MULTILINE)
#     if result and result.group('oper') is not None:
#         # Recurse
#         logger.info(f"L{level}: {result.group('oper')} Rest: {result.group('rest')} Recurse")
#         recparse(result.group('rest'), level=level+1)
#     else:
#         iter = re.finditer(inner_pattern, rule, re.IGNORECASE | re.MULTILINE)
#         #regex = r"^\s*(?P<oper>ANY|ALL)?\s*{?(?P<inner>[\w'\s.]+=[\s\w'.]+)}?\s*$"
#         #regex = r"^\s*(?P<oper>ANY|ALL)\s*{(?P<condition>[\w'\s.]+=[\s\w'.]+)|(\s*,?\s*)}\s*$"
#     #result = re.search(regex, rule, re.IGNORECASE | re.MULTILINE)
#         #iter = re.finditer(regex, rule, re.IGNORECASE | re.MULTILINE)
#         for result in iter:
#             logger.info(f"L{level} Operator: {result.group('oper')} Exp: {result.group('condition')} Fall back")
#         # if result and result.group('oper') is not None:
#         #     logger.info(f"L{level} Operator: {result.group('oper')} Exp: {result.group('inner')}")
#         #     recparse(result.group('inner'), level=level+1)
#         # elif result and result.group('oper') is None:
#         #     #recparse(result.group('inner'), level=level+1)
#         #     logger.info(f"L{level} Exp: {result.group('inner')} (Fall Back)")
#         # else:
#         #     logger.info(f"Falling back")

# if __name__ == "__main__":

#     # Main Logger
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s [%(threadName)s] %(levelname)s %(message)s')
#     logger = logging.getLogger('oci-dynamic-group-analysis-main')

#     local_policies = policy.PolicyAnalysis(progress=None, verbose=False)
#     local_policies.initialize_client("DEFAULT", False)
#     local_policies.load_policies_from_client(use_cache=True, use_recursion=False)
    
#     logger.info(f"Policy Statement Count: {len(local_policies.regular_statements)}")

#     local_dg = DynamicGroupAnalysis(verbose=False)
#     local_dg.initialize_client(profile="DEFAULT",
#                                use_instance_principal=False)
#     local_dg.set_statements(statements=local_policies.regular_statements)
    
#     logger.info(f"Initialized client")

#     successful_load = local_dg.load_all_dynamic_groups(use_cache=True)

#     logger.info(f"Loaded DG success: {successful_load}.  Total: {len(local_dg.dynamic_groups)}")

#     tic = time.perf_counter()
#     local_dg.run_dg_in_use_analysis()
#     toc = time.perf_counter()
#     logger.info(f"Ran In Use Analysis in {toc-tic:.2f}s")

#     tic = time.perf_counter()
#     # local_dg.run_deep_analysis()
#     toc = time.perf_counter()

#     logger.info(f"Ran Deep Analysis in {toc-tic:.2f}s")

#     for dg in local_dg.dynamic_groups:
#         if not dg[4] or len(dg[5]) > 0: 
#             # Only print invalid ones
#             logger.info(f"Rule: {dg[0]} In use: {dg[4]} Invalid OCIDs: {len(dg[5])}")


#         # logger.info(f"----Started recursion: {rule}")
#         # recparse(rule=rule, level=0)
#         # logger.info(f"----Finished recursion")
