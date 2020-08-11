# streams: API URL endpoints to be called
# properties:
#   <root node>: Plural stream name for the endpoint
#   path: API endpoint relative path, when added to the base URL, creates the full path
#   key_properties: Primary key field(s) for the object endpoint
#   replication_method: FULL_TABLE or INCREMENTAL
#   replication_keys: bookmark_field(s), typically a date-time, used for filtering the results
#        and setting the state
#   params: Query, sort, and other endpoint specific parameters
#   data_key: JSON element containing the records for the endpoint
#   bookmark_query_field: Typically a date-time field used for filtering the query
#   bookmark_type: Data type for bookmark, integer or datetime
#   children: A collection of child endpoints (where the endpoint path includes the parent id)
#   parent: On each of the children, the singular stream name for parent element
STREAMS = {
    # Reference: https://merchant.tradetracker.com/webService/index/method/getCampaigns
    'campaigns': {
        'key_properties': ['ID'],
        'replication_method': 'FULL_TABLE',
        'children': {
            # Reference: https://merchant.tradetracker.com/webService/index/method/getReportAffiliateSite
            'campaign_report': {
                'key_properties': ['date'],
                'replication_method': 'INCREMENTAL',
                'replication_keys': ['date'],
                'date_window_size': 1,
                'parent': 'campaign_id'
            },
            # Reference: https://merchant.tradetracker.com/webService/index/method/getAffiliateSites
            'affiliate_sites': {
                'key_properties': ['ID'],
                'replication_method': 'FULL_TABLE',
                'parent': 'campaign_id'
            }
        }
    }
}

# De-nest children nodes for Discovery mode
def flatten_streams():
    flat_streams = {}
    # Loop through parents
    for stream_name, endpoint_config in STREAMS.items():
        flat_streams[stream_name] = endpoint_config
        # Loop through children
        children = endpoint_config.get('children')
        if children:
            for child_stream_name, child_endpoint_config in children.items():
                flat_streams[child_stream_name] = child_endpoint_config
                flat_streams[child_stream_name]['parent_stream'] = stream_name

    return flat_streams
