from diagrams import Cluster, Diagram, Edge
from diagrams.onprem.analytics import Spark
from diagrams.onprem.compute import Server
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.aggregator import Fluentd
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.network import Nginx
from diagrams.onprem.queue import Kafka

from diagrams.oci.compute import VM
from diagrams.oci.monitoring import Telemetry
from diagrams.oci.network import LoadBalancer,Vcn
from diagrams.oci.governance import Compartments

regions = ["1","2"]
compartments = ["A","B"]
vcns = ["vcn1","vcn2"]

with Diagram("Advanced Web Service with On-Premise", show=False, direction="TB"):

    for reg in regions:
        # Rgeional
        

        with Cluster(label=f"OCI Region: {reg}",
                     direction="RL"):
            
            for comp in compartments:
                with Cluster(label=f"OCI Comp: {comp}",
                             direction="LR",):
                    telem = Telemetry("OCI Metrics")
                    

                    for vcn in vcns:
                        with Cluster(label=f"OCI VCN: {vcn}",
                                     direction="TB"):
                            ingress = LoadBalancer("OCI LB")
                            mult = [VM("one"),VM("two"),VM("three")]
        
                            ingress >> mult >> Edge(color="firebrick", style="dashed") >> telem
                        

