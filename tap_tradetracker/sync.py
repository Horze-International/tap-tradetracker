import math
from datetime import datetime,timedelta
import humps

import singer
from singer import metrics, metadata, Transformer, utils
from singer.utils import strptime_to_utc, strftime

from tap_tradetracker.client import TradeTrackerClient
from tap_tradetracker.streams import flatten_streams, STREAMS

LOGGER = singer.get_logger()


def write_schema(catalog, stream_name):
    stream = catalog.get_stream(stream_name)
    schema = stream.schema.to_dict()
    try:
        singer.write_schema(stream_name, schema, stream.key_properties)
    except OSError as err:
        LOGGER.error('OS Error writing schema for: {}'.format(stream_name))
        raise err

def write_record(stream_name, record, time_extracted):
    try:
        singer.messages.write_record(stream_name, record, time_extracted=time_extracted)
    except OSError as err:
        LOGGER.error('OS Error writing record for: {}'.format(stream_name))
        LOGGER.error('Stream: {}, record: {}'.format(stream_name, record))
        raise err
    except TypeError as err:
        LOGGER.error('Type Error writing record for: {}'.format(stream_name))
        LOGGER.error('Stream: {}, record: {}'.format(stream_name, record))
        raise err

def get_bookmark(state, stream, default, bookmark_field=None, parent_id=None):
    if (state is None) or ('bookmarks' not in state):
        return default

    if bookmark_field is None:
        return default

    if parent_id:
        key = '{}(parent:{})'.format(bookmark_field, parent_id)
    else:
        key = bookmark_field

    return (
        state
        .get('bookmarks', {})
        .get(stream, {})
        .get(key, default)
    )

def write_bookmark(state, stream, value, bookmark_field=None, parent_id=None):
    if parent_id:
        key = '{}(parent:{})'.format(bookmark_field, parent_id)
    else:
        key = bookmark_field
    if 'bookmarks' not in state:
        state['bookmarks'] = {}
    if stream not in state['bookmarks']:
        state['bookmarks'][stream] = {}

    state['bookmarks'][stream][key] = value
    LOGGER.info('Write state for Stream: {}, Parent ID: {}, value: {}'.format(
        stream, parent_id, value))
    singer.write_state(state)

def process_records(catalog, #pylint: disable=too-many-branches
                    stream_name,
                    records,
                    time_extracted,
                    bookmark_field=None,
                    max_bookmark_value=None,
                    last_datetime=None):
    stream = catalog.get_stream(stream_name)
    schema = stream.schema.to_dict()
    stream_metadata = metadata.to_map(stream.metadata)

    with metrics.record_counter(stream_name) as counter:
        for record in records:
            # Transform record for Singer.io
            with Transformer() as transformer:
                transformed_record = transformer.transform(
                    record,
                    schema,
                    stream_metadata)

                # Reset max_bookmark_value to new value if higher
                if bookmark_field and (bookmark_field in transformed_record):
                    bookmark_date = transformed_record.get(bookmark_field)
                    bookmark_dttm = strptime_to_utc(bookmark_date)

                    if not max_bookmark_value:
                        max_bookmark_value = last_datetime

                    max_bookmark_dttm = strptime_to_utc(max_bookmark_value)

                    if bookmark_dttm > max_bookmark_dttm:
                        max_bookmark_value = strftime(bookmark_dttm)

                write_record(stream_name, transformed_record, time_extracted=time_extracted)
                counter.increment()

        LOGGER.info('Stream: {}, Processed {} records'.format(stream_name, counter.value))
        return max_bookmark_value, counter.value

# Sync a specific parent or child endpoint.
def sync_endpoint(
        client,
        config,
        catalog,
        state,
        stream_name,
        endpoint_config,
        sync_streams,
        selected_streams,
        timezone_desc=None,
        parent_id=None):

    # endpoint_config variables
    bookmark_field = next(iter(endpoint_config.get('replication_keys', [])), None)
    data_key_record = endpoint_config.get('data_key_record')
    id_fields = endpoint_config.get('key_properties')
    parent = endpoint_config.get('parent')
    date_window_size = endpoint_config.get('date_window_size')

    # tap config variabless
    start_date = config.get('start_date')
    attribution_window = config.get('attribution_window', 30)

    last_datetime = get_bookmark(state, stream_name, start_date, bookmark_field, parent_id)
    max_bookmark_value = last_datetime

    # Convert to datetimes in local/ad account timezone
    now_datetime = utils.now()
    last_dttm = strptime_to_utc(last_datetime)

    if stream_name.endswith('_report'):
        # date_window_size: Number of days in each date window
        # Set start window
        start_window = now_datetime - timedelta(days=attribution_window)
        if last_dttm < start_window:
            start_window = last_dttm
        # Set end window
        end_window = start_window + timedelta(days=date_window_size)

    else:
        start_window = last_dttm
        end_window = now_datetime
        diff_sec = (end_window - start_window).seconds
        date_window_size = math.ceil(diff_sec / (3600 * 24)) # round-up difference to days

    total_records = 0

    while start_window < now_datetime:
        LOGGER.info('START Sync for Stream: {}{}'.format(
            stream_name,
            ', Date window from: {} to {}'.format(start_window.date(), end_window.date()) \
                if stream_name.endswith('_report') else ''))

        data = []
        if stream_name == 'campaigns':
            data = client.get_campaigns()
        elif stream_name == 'campaign_report':
            date_from = start_window.date()
            date_to = (end_window - timedelta(days=1)).date()
            if date_to < date_from:
                date_to = date_from
            result = client.get_report_campaign(parent_id, date_from=date_from, date_to=date_to)
            data.append(result)
        else:
            raise Exception(f'Not supported stream: {stream_name}')

        # time_extracted: datetime when the data was extracted from the API
        time_extracted = utils.now()
        if not data or data is None or data == []:
            LOGGER.info('No data results returned')
            total_records = 0
        else:
            # Process records and get the max_bookmark_value and record_count
            if stream_name in sync_streams:

                # Transform data
                transformed_data = [] # initialize the record list

                for data_record in data:
                    if data_key_record:
                        record = data_record.get(data_key_record, {})
                    else:
                        record = data_record

                    # Add parent id field/value
                    if parent and parent_id and parent not in record:
                        record[parent] = parent_id

                    if stream_name.endswith('_report'):
                        if start_window == end_window - timedelta(days=1):
                            record['date'] = start_window.strftime('%Y-%m-%d')
                        else:
                            record['start_date'] = start_window.strftime('%Y-%m-%d')
                            record['end_date'] = (end_window - timedelta(days=1)).strftime('%Y-%m-%d')

                    # transform record (remove inconsistent use of CamelCase)
                    try:
                        transformed_record = humps.decamelize(record)
                    except Exception as err:
                        LOGGER.error('{}'.format(err))
                        LOGGER.error('error record: {}'.format(record))
                        raise Exception(err)

                    transformed_data.append(transformed_record)

                # LOGGER.info('transformed_data = {}'.format(transformed_data)) # COMMENT OUT
                if not transformed_data or transformed_data is None:
                    LOGGER.info('No transformed data for data = {}'.format(data))
                    total_records = 0
                    #break # No transformed_data results
                else:
                    max_bookmark_value, record_count = process_records(catalog=catalog,
                                    stream_name=stream_name,
                                    records=transformed_data,
                                    time_extracted=time_extracted,
                                    bookmark_field=bookmark_field,
                                    max_bookmark_value=max_bookmark_value,
                                    last_datetime=last_datetime)
                    LOGGER.info('Stream {}, batch processed {} records'.format(
                        stream_name, record_count))

                    # Loop thru parent batch records for each children objects (if should stream)
                    children = endpoint_config.get('children')
                    if children:
                        for child_stream_name, child_endpoint_config in children.items():
                            if child_stream_name in sync_streams:
                                LOGGER.info('START Syncing: {}'.format(child_stream_name))
                                write_schema(catalog, child_stream_name)

                                # For each parent record
                                for record in data:
                                    i = 0
                                    # Set parent_id
                                    for id_field in id_fields:
                                        if i == 0:
                                            parent_id_field = id_field
                                        if id_field == 'id':
                                            parent_id_field = id_field
                                        i = i + 1
                                    parent_id = record.get(parent_id_field)

                                    # sync_endpoint for child
                                    LOGGER.info(
                                        'START Sync for Stream: {}, parent_stream: {}, parent_id: {}'\
                                            .format(child_stream_name, stream_name, parent_id))

                                    child_total_records = sync_endpoint(
                                        client=client,
                                        config=config,
                                        catalog=catalog,
                                        state=state,
                                        stream_name=child_stream_name,
                                        endpoint_config=child_endpoint_config,
                                        sync_streams=sync_streams,
                                        selected_streams=selected_streams,
                                        timezone_desc=timezone_desc,
                                        parent_id=parent_id)

                                    LOGGER.info(
                                        'FINISHED Sync for Stream: {}, parent_id: {}, total_records: {}'\
                                            .format(child_stream_name, parent_id, child_total_records))
                                    # End transformed data record loop
                                # End if child in sync_streams
                            # End child streams for parent
                        # End if children

        # Update the state with the max_bookmark_value for the stream date window
        # Snapchat Ads API does not allow page/batch sorting; bookmark written for date window
        if bookmark_field and stream_name in selected_streams:
            write_bookmark(state, stream_name, max_bookmark_value, bookmark_field, parent_id)

        # Increment date window and sum endpoint_total
        start_window = end_window
        next_end_window = end_window + timedelta(days=date_window_size)
        if next_end_window > now_datetime:
            end_window = now_datetime
        else:
            end_window = next_end_window
        # End date window

    return total_records

# Currently syncing sets the stream currently being delivered in the state.
# If the integration is interrupted, this state property is used to identify
#  the starting point to continue from.
# Reference: https://github.com/singer-io/singer-python/blob/master/singer/bookmarks.py#L41-L46
def update_currently_syncing(state, stream_name):
    if (stream_name is None) and ('currently_syncing' in state):
        del state['currently_syncing']
    else:
        singer.set_currently_syncing(state, stream_name)
    singer.write_state(state)

def sync(client, config, catalog, state):
    # Get selected_streams from catalog, based on state last_stream
    #   last_stream = Previous currently synced stream, if the load was interrupted
    last_stream = singer.get_currently_syncing(state)
    LOGGER.info('last/currently syncing stream: {}'.format(last_stream))
    selected_streams = []
    for stream in catalog.get_selected_streams(state):
        selected_streams.append(stream.stream)
    LOGGER.info('selected_streams: {}'.format(selected_streams))
    if not selected_streams or selected_streams == []:
        return

    # Get the streams to sync (based on dependencies)
    sync_streams = []
    flat_streams = flatten_streams()
    # Loop thru all streams
    for stream_name, stream_metadata in flat_streams.items():
        # If stream has a parent_stream, then it is a child stream
        parent_stream = stream_metadata.get('parent_stream')

        if stream_name in selected_streams:
            LOGGER.info('stream: {}, parent: {}'.format(
                stream_name, parent_stream))
            if stream_name not in sync_streams:
                sync_streams.append(stream_name)
            if parent_stream and parent_stream not in sync_streams:
                sync_streams.append(parent_stream)
    LOGGER.info('Sync Streams: {}'.format(sync_streams))

    LOGGER.info('Initializing TradeTrackerClient client - Loading WSDL')
    with TradeTrackerClient(customer_id=config['customer_id'],
                                passphrase=config['passphrase'],
                                sandbox=config.get('sandbox', False),
                                locale=config.get('locale'),
                                demo=config.get('demo', False)) as client:

        LOGGER.info('Authenticate against API')
        client.authenticate()

        # Loop through selected_streams
        # Loop through endpoints in selected_streams
        for stream_name, endpoint_config in STREAMS.items():
            if stream_name in sync_streams:
                LOGGER.info('START Syncing: {}'.format(stream_name))
                write_schema(catalog, stream_name)
                update_currently_syncing(state, stream_name)

                total_records = sync_endpoint(
                    client=client,
                    config=config,
                    catalog=catalog,
                    state=state,
                    stream_name=stream_name,
                    endpoint_config=endpoint_config,
                    sync_streams=sync_streams,
                    selected_streams=selected_streams)

                update_currently_syncing(state, None)
                LOGGER.info('FINISHED Syncing: {}, total_records: {}'.format(
                    stream_name,
                    total_records))
