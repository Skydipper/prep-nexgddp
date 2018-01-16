"""QUERY SERVICE"""

import json
import os
import logging
import tempfile
import datetime
import dateutil.parser
from requests import Request, Session
from requests.exceptions import ConnectTimeout
from nexgddp.errors import SqlFormatError, PeriodNotValid, TableNameNotValid, GeostoreNeeded, RasdamanError
from nexgddp.helpers.gdal_helper import GdalHelper
# from nexgddp.helpers.requests_helper import requests_retry_session
from nexgddp.helpers.coloring_helper import ColoringHelper
from nexgddp.services.xml_service import XMLService
from CTRegisterMicroserviceFlask import request_to_microservice
import dateutil.parser
from osgeo import gdal, gdalnumeric

RASDAMAN_URL = os.getenv('RASDAMAN_URL')

# Allows gdal to use exceptions
gdal.UseExceptions()

class QueryService(object):
    @staticmethod
    def get_stats(scenario, model, years, indicator, bbox, function):
        logging.info('[QueryService] Getting aggregated temporal series from rasdaman')
        year_min = sorted(years)[0]
        year_max = sorted(years)[-1]
        logging.info(year_min)
        logging.info(year_max)
        results = []
        if bbox == []:
            raise GeostoreNeeded("No latitude and longitude provided")
        else:
            bbox_str = f",Lat({bbox[0]}),Long({bbox[1]})"
            # IMPORTANT - Rasdaman tablename must be in this format ->
            query = f"for cov in ({scenario}_{model}_processed) return encode( {function}((cov.{indicator})[ ansi(\"{year_min}\":\"{year_max}\") {bbox_str}]), \"CSV\")"
            logging.info('Running the query ' + query)
            raster_filename = QueryService.get_rasdaman_query(query)
            try:
                datafile = open(raster_filename, "r")
                raw_data = datafile.read()
                processed_data = raw_data.replace('{', '').replace('}', '').split(',')
            finally:
                source_raster = None
                # Removing the raster
                os.remove(os.path.join('/tmp', raster_filename))
        return map(float, processed_data)
        return results

    @staticmethod
    def get_histogram(scenario, model, years, indicator, bbox):
        logging.info('[QueryService] Getting histogram from rasdaman')
        results = []

        for year in years:
            if bbox == []:
                bbox_str = ""
            else:
                bbox_str = f",Lat({bbox[0]}:{bbox[2]}),Long({bbox[1]}:{bbox[3]})"
            query = f"for cov in ({scenario}_{model}_processed) return encode( (cov.{indicator})[ ansi(\"{year}\") {bbox_str}], \"GTiff\")"
            logging.info('Running the query ' + query)
            raster_filename = QueryService.get_rasdaman_query(query)
            try:
                source_raster = gdal.Open(raster_filename)
                all_results = GdalHelper.calc_histogram(source_raster)
                all_results["year"] = year
                results.append(all_results)
            finally:
                source_raster = None
                # Removing the raster
                os.remove(os.path.join('/tmp', raster_filename))
        return results

    @staticmethod
    def get_temporal_series(scenario, model, years, indicator, bbox):
        logging.info('[QueryService] Getting temporal series from rasdaman')
        year_min = sorted(years)[0].replace("'", '') if type(sorted(years)[0]) == 'string' else sorted(years)[0]
        year_max = sorted(years)[-1].replace("'", '') if type(sorted(years)[-1]) == 'string' else sorted(years)[-1]
        logging.info(year_min)
        logging.info(year_max)
        results = []
        if bbox == []:
            raise GeostoreNeeded("No latitude and longitude provided")
        else:
            bbox_str = f",Lat({bbox[0]}),Long({bbox[1]})"
            ansidate_str = f"ansi(\"{year_min}\":\"{year_max}\")" if year_min != year_max else f"ansi(\"{year_min}\")"
            query = f"for cov in ({scenario}_{model}_processed) return encode( (cov.{indicator})[ {ansidate_str} {bbox_str}], \"CSV\")"
            logging.info('Running the query ' + query)
            raster_filename = QueryService.get_rasdaman_query(query)
            try:
                datafile = open(raster_filename, "r")
                raw_data = datafile.read()
                processed_data = raw_data.replace('{', '').replace('}', '').split(',')
            finally:
                source_raster = None
                # Removing the raster
                os.remove(os.path.join('/tmp', raster_filename))
        return map(float, processed_data)

    @staticmethod
    def get_all_data(scenario, model, years, bbox):
        logging.info('[QueryService] Getting * data from rasdaman')
        year_min = sorted(years)[0]
        year_max = sorted(years)[-1]
        results = []
        if bbox == []:
            raise GeostoreNeeded("No latitude and longitude provided")
        else:
            bbox_str = f",Lat({bbox[0]}),Long({bbox[1]})"
            query = f"for cov in ({scenario}_{model}_processed) return encode( (cov)[ ansi(\"{year_min}\":\"{year_max}\") {bbox_str}], \"CSV\")"
            logging.info('Running the query ' + query)
            raster_filename = QueryService.get_rasdaman_query(query)
            try:
                output = {}
                datafile = open(raster_filename, "r")
                raw_data = datafile.read()
                processed_data = raw_data.replace('{', '').replace('}', '').split(',')
                fields_xml = QueryService.get_rasdaman_fields(scenario, model)
                fields = XMLService.get_fields(fields_xml)
                fields_without_year = dict((i,fields[i]) for i in fields if i!='year')
                varnames = list()
                for key in fields_without_year:
                    varnames.append(key)

                logging.debug(f"varnames: {varnames}")
                results = [{} for _ in range(len(years))]
                ansi_years = list(map(lambda x: dateutil.parser.parse(f"{x}-01-01").isoformat(), years))
                logging.debug(ansi_years)
                logging.debug(f"years: {years}")
                logging.debug(f"processed_data: {processed_data}")
                data_array = list()

                for element in processed_data:
                    data_array.append(list( map(float, element.replace('"', '').split(' '))))
                    logging.debug(data_array)

                processed_obj = list(map(lambda x: dict(zip(varnames, x)), data_array))
                # logging.debug(processed_obj)

                for i in range(len(years)):
                    results[i]['year'] = dateutil.parser.parse(f"{years[i]}-01-01").isoformat()
                    results[i].update(processed_obj[i])
            finally:
                source_raster = None
                # Removing the raster. Really important!
                os.remove(os.path.join('/tmp', raster_filename))
        return results

    @staticmethod
    def get_rasdaman_query(query):
        logging.info('[QueryService] Executing rasdaman query')
        payload_arr = ['<?xml version="1.0" encoding="UTF-8" ?>',
                       '<ProcessCoveragesRequest xmlns="http://www.opengis.net/wcps/1.0" service="WCPS" version="1.0.0">',
                       '<query><abstractSyntax>',
                       query,
                       '</abstractSyntax></query>',
                       '</ProcessCoveragesRequest>']
        payload = ''.join(payload_arr)
        headers = {'Content-Type': 'application/xml'}
        request = Request(
            method='POST',
            url=RASDAMAN_URL,
            data=payload,
            headers=headers
        )
        session = Session()
        prepped = session.prepare_request(request)
        response = session.send(prepped)
        if response.status_code == 404:
            raise PeriodNotValid('Period Not Valid')

        with tempfile.NamedTemporaryFile(suffix='.tiff', delete=False) as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)
            raster_filename = f.name
            logging.debug(f"[QueryService] Temporary raster filename: {raster_filename}")
            f.close()
            return raster_filename

    @staticmethod
    def get_rasdaman_csv_query(query):
        logging.info('[QueryService] Executing rasdaman query')
        payload_arr = ['<?xml version="1.0" encoding="UTF-8" ?>',
                       '<ProcessCoveragesRequest xmlns="http://www.opengis.net/wcps/1.0" service="WCPS" version="1.0.0">',
                       '<query><abstractSyntax>',
                       query,
                       '</abstractSyntax></query>',
                       '</ProcessCoveragesRequest>']
        payload = ''.join(payload_arr)
        headers = {'Content-Type': 'application/xml'}
        request = Request(
            method='POST',
            url=RASDAMAN_URL,
            data=payload,
            headers=headers
        )
        session = Session()
        prepped = session.prepare_request(request)
        response = session.send(prepped)
        return response.text

    @staticmethod
    def get_tile_query(bbox, year, model, scenario, indicator, bounds):
        logging.info('[QueryService] Forming rasdaman query')
        coverage = f'{scenario}_{model}_processed'
        logging.debug(f'coverage: {coverage}')
        query_list = [
            'for cov in (',
            coverage,
            ') return encode(scale((((cov.',
            indicator,
            ')[ansi("',
            year,
            '"),Lat(',
            str(bbox['lat'][0]),
            ':',
            str(bbox['lat'][1]),
            '),Long(',
            str(bbox['lon'][0]),
            ':',
            str(bbox['lon'][1]),
            ')]',
            ColoringHelper.normalize(
                * bounds
            ),
            ', {Lat: "CRS:1"(0:255), Long: "CRS:1"(0:255)}),  "PNG")]'
        ]

        envelope_list = [ '<?xml version="1.0" encoding="UTF-8" ?>',
                          '<ProcessCoveragesRequest xmlns="http://www.opengis.net/wcps/1.0" service="WCPS" version="1.0.0">',
                          '<query><abstractSyntax>',
                          *query_list,
                          '</abstractSyntax></query>',
                          '</ProcessCoveragesRequest>'
        ]

        payload = ''.join(envelope_list)
        logging.debug(f"payload: {payload}")
        headers = {'Content-Type': 'application/xml'}
        request = Request(
            method='POST',
            url=RASDAMAN_URL,
            data=payload,
            headers=headers
        )
        session = Session()
        prepped = session.prepare_request(request)
        response = session.send(prepped)
        if response.status_code == 404:
            raise PeriodNotValid('Data not found')
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)
            raster_filename = f.name
            logging.debug(f"[QueryService] Temporary raster filename: {raster_filename}")
            f.close()
            return raster_filename

    @staticmethod
    def get_tile_diff_query(bbox, year, model, scenario, indicator, bounds, year_b, dset_b):
        logging.info('[QueryService] Forming rasdaman query')
        coverage_a = f'{scenario}_{model}_processed'
        logging.debug(f'coverage_a: {coverage_a}')
        logging.debug(f'coverage_b: {dset_b}')
        logging.debug(f'bounds: {bounds}')

        lower_bound_expr = ' - ' + str(bounds[0]) if float(bounds[0]) >= 0 else str( ' + ' +  str(abs(bounds[0])) )
        logging.debug(lower_bound_expr)
        bounds_range = str(float(bounds[1]) - float(bounds[0]))
        logging.debug(bounds_range)
        # x := (c - a) / (b - a)
        bbox_expr = f" Lat({bbox['lat'][0]}:{bbox['lat'][1]}),Long({bbox['lon'][0]}:{bbox['lon'][1]})]"
        query = ''.join([
            f"for cov1 in ({dset_b}), cov2 in ({coverage_a}) return encode(scale(",
            f"(((cov1.{indicator})[ansi(\"{year_b}\"),",
            bbox_expr,
            f" - (cov2.{indicator})[ansi(\"{year}\"),",
            bbox_expr,
            f") {lower_bound_expr} ) * (255 / ({bounds_range} )),",
            "{Lat: \"CRS:1\"(0:255), Long: \"CRS:1\"(0:255)}),\"PNG\")]" # Not a f-expression
            ])

        logging.debug(query)

        envelope_list = [ '<?xml version="1.0" encoding="UTF-8" ?>',
                          '<ProcessCoveragesRequest xmlns="http://www.opengis.net/wcps/1.0" service="WCPS" version="1.0.0">',
                          '<query><abstractSyntax>',
                          query,
                          '</abstractSyntax></query>',
                          '</ProcessCoveragesRequest>'
        ]

        payload = ''.join(envelope_list)
        logging.debug(f"payload: {payload}")
        headers = {'Content-Type': 'application/xml'}
        request = Request(
            method='POST',
            url=RASDAMAN_URL,
            data=payload,
            headers=headers
        )
        session = Session()
        prepped = session.prepare_request(request)
        response = session.send(prepped)
        if response.status_code == 404:
            raise PeriodNotValid('Data not found')
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)
            raster_filename = f.name
            logging.debug(f"[QueryService] Temporary raster filename: {raster_filename}")
            f.close()
            return raster_filename


    @staticmethod
    def get_rasdaman_fields(scenario, model):
        # Need to parse xml
        logging.info(f"[QueryService] Getting fields for scenario {scenario} and model {model}")
        headers = {'Content-Type': 'application/xml'}
        params = {
            'SERVICE': 'WCS',
            'VERSION': '2.0.1',
            'REQUEST': 'DescribeCoverage',
            'COVERAGEID': f"{scenario}_{model}_processed"
        }
        request = Request(
            method='GET',
            url=RASDAMAN_URL,
            headers=headers,
            params=params
        )
        session = Session()
        prepped = session.prepare_request(request)
        try:
            response = session.send(prepped, timeout=15)
        except ConnectTimeout:
            raise RasdamanError('Rasdaman not reachable')
        if response.status_code == 404:
            raise TableNameNotValid('Table Name Not Valid')
        output = response.text
        return output

    @staticmethod
    def convert(query):
        logging.info('Converting Query: '+query)
        try:
            config = {
                'uri': '/convert/sql2SQL?sql='+query,
                'method': 'GET'
            }
            response = request_to_microservice(config)
        except Exception as error:
            raise error

        if response.get('errors'):
            errors = response.get('errors')
            raise SqlFormatError(message=errors[0].get('detail'))

        query = response.get('data', None)
        s_query = query.get('attributes', {}).get('query')
        json_sql = query.get('attributes', {}).get('jsonSql')
        return s_query, json_sql

    @staticmethod
    def get_clone_url(dataset_id, query):
        return {
            'httpMethod': 'POST',
            'url': '/v1/dataset/'+dataset_id+'/clone',
            'body': {
                'dataset': {
                    'datasetUrl': '/query/'+dataset_id+'?sql='+query,
                    'application': [
                        'your',
                        'apps'
                    ]
                }
            }
        }

    @staticmethod
    def get_domain(scenario, model):
        logging.info(f"Obtaining domain for the scenario {scenario}, and model {model}")
        domain_xml = QueryService.get_rasdaman_fields(scenario, model)
        domain = XMLService.get_domain(domain_xml)
        domain_data = {
            "lat": {
                "max": domain.get('upperCorner')[0],
                "min": domain.get('lowerCorner')[0]
            },
            "lon": {
                "max": domain.get('upperCorner')[1],
                "min": domain.get('lowerCorner')[1]
            },
            "year": {
                "max": dateutil.parser.parse(domain.get('upperCorner')[2]).isoformat(),
                "min": dateutil.parser.parse(domain.get('lowerCorner')[2]).isoformat()
            }
        }
        return domain_data
