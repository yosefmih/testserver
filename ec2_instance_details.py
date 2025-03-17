import boto3
import json
import re

def get_instance_details(instance_type):
    # Initialize the pricing client
    pricing_client = boto3.client('pricing', region_name='us-east-1')
    
    # Set up the filters for our query
    filters = [
        {'Type': 'TERM_MATCH', 'Field': 'ServiceCode', 'Value': 'AmazonEC2'},
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
        {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
        {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'}
    ]
    
    # Query the pricing API
    response = pricing_client.get_products(
        ServiceCode='AmazonEC2',
        Filters=filters
    )
    
    # Process the response
    if not response['PriceList']:
        print(f"No pricing data found for {instance_type}")
        return None
    
    # Parse the first product in the price list
    product_info = json.loads(response['PriceList'][0])
    attributes = product_info['product']['attributes']
    
    # Extract CPU, memory, and GPU info
    vcpu = int(attributes.get('vcpu', 0))
    
    # Parse memory (comes as string like "16 GiB")
    memory_str = attributes.get('memory', '0 GiB')
    memory_match = re.match(r'(\d+(?:\.\d+)?)\s+GiB', memory_str)
    memory_gib = float(memory_match.group(1)) if memory_match else 0
    memory_mib = int(memory_gib * 1024)
    
    # GPU count (might not be present for all instances)
    gpu = int(attributes.get('gpu', 0))
    
    # Extract other useful information
    family = attributes.get('instanceFamily', '')
    generation = attributes.get('currentGeneration', '')
    
    # Print details
    print(f"Instance Type: {instance_type}")
    print(f"Family: {family}")
    print(f"Current Generation: {generation}")
    print(f"vCPUs: {vcpu}")
    print(f"Memory: {memory_gib} GiB ({memory_mib} MiB)")
    print(f"GPUs: {gpu}")
    print(f"Network Performance: {attributes.get('networkPerformance', 'N/A')}")
    
    # Return a structured result
    return {
        'InstanceType': instance_type,
        'Family': family,
        'vCPUs': vcpu,
        'MemoryMiB': memory_mib,
        'GPUs': gpu,
        'NetworkPerformance': attributes.get('networkPerformance', 'N/A')
    }

# Test with a few different instance types
instance_types = ['t3.medium', 'm5.large', 'p3.2xlarge', 'g4dn.xlarge']
for instance_type in instance_types:
    print("\n" + "="*50)
    result = get_instance_details(instance_type)
    if result:
        print(f"Successfully retrieved details for {instance_type}")