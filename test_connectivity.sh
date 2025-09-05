RG=jphaugla-crdb-rg
NAMESPACE=jphaugla-crdb-ehns
ZONE=privatelink.servicebus.windows.net
VNET=jphaugla-crdb-network
# Guess for your PE name from Terraform pattern; confirm below:
PE=jphaugla-crdb-eh-pep

# 0) Sanity: which PE name do I actually have?
az network private-endpoint list -g $RG -o table

# 1) VM-side DNS should return the **private** IP (192.168.3.4)
getent hosts ${NAMESPACE}.servicebus.windows.net
nslookup ${NAMESPACE}.servicebus.windows.net

