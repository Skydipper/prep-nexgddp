"""MIDDLEWARE"""

from functools import wraps
from flask import request, redirect

from nexgddp.routes.api import error
from nexgddp.services.geostore_service import GeostoreService
from nexgddp.services.redis_service import RedisService
from nexgddp.services.layer_service import LayerService
from nexgddp.services.dataset_service import DatasetService
from nexgddp.errors import GeostoreNotFound, InvalidCoordinates, LayerNotFound

import logging

def get_bbox_by_hash(func):
    """Get geodata"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        geostore = request.args.get('geostore', None)
        if not geostore:
            bbox = []
        else:
            try:
                _, bbox = GeostoreService.get(geostore)
            except GeostoreNotFound:
                return error(status=404, detail='Geostore not found')

        kwargs["bbox"] = bbox
        return func(*args, **kwargs)
    return wrapper


def get_latlon(func):
    """Get geodata"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        geostore = request.args.get('geostore', None)
        lat = request.args.get('lat', None)
        lon = request.args.get('lon', None)
        if not geostore and not (lat and lon):
            kwargs["bbox"] = None
            return func(*args, **kwargs)
        if not geostore:
            bbox = [lat, lon]
            kwargs["bbox"] = bbox
        return func(*args, **kwargs)
    return wrapper


def get_year(func):
    """Get geodata"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        year = request.args.get('year', None)
        kwargs["year"] = year
        logging.debug(f"year: {year}")
        if not year:
            kwargs["year"] = None
        return func(*args, **kwargs)
    return wrapper

def get_tile_attrs(func):
    """Get style"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        layer_object = kwargs.get('layer_object', None)
        layer_config = layer_object.get('layerConfig', None)
        dataset = layer_object.get('dataset', None)
        logging.debug(f'dataset: {dataset}')

        logging.debug('Obtaining style')
        layer_style = layer_config.get('colorRamp')
        logging.debug(layer_style)
        kwargs["style"] = layer_style

        logging.debug('Obtaining year')
        # year = layer_config.get('year')
        # logging.debug(f'year: {year}')
        # kwargs["year"] = year
        logging.debug('Obtaining indicator')
        indicator = layer_config.get('indicator')
        logging.debug(f'indicator: {indicator}')
        kwargs["indicator"] = indicator

        logging.debug('Obtaining scenario and model')
        dataset_object = DatasetService.get(dataset)
        tablename = dataset_object.get('tableName', None)
        logging.debug(f'tablename: {tablename}')
        kwargs['model'] = tablename.split('/')[1]
        kwargs['scenario'] = tablename.split('/')[0]

        is_comparison = layer_config.get('compareWith')
        logging.debug(f"is_comparison: {is_comparison}")
        if is_comparison:
            compare_year = request.args.get('compareYear', None)
            kwargs["compare_year"] = str(compare_year)
            logging.debug(f"compare_year: {compare_year}")
            dataset_b_id = request.args.get('compareTo', None)
            if dataset_b_id:
                dataset_b_object = DatasetService.get(dataset_b_id)
                tablename_b = '_'.join(dataset_b_object.get('tableName', None).split('/')) + '_processed'
                kwargs["dset_b"] = tablename_b
                logging.debug(f"tablename_b: {tablename_b}")
            else:
                kwargs["dset_b"] = None
        del kwargs["layer_object"]
        return func(*args, **kwargs)
    return wrapper

def get_diff_attrs(func):
    """Get style"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        req_body = request.get_json(force=True)
        logging.debug(req_body)
        dset_a = request.get_json().get('dset_a')
        dataset_object_a = DatasetService.get(dset_a)
        tablename_a =  '_'.join(dataset_object_a.get('tableName').split('/')) + '_processed'
        logging.debug(tablename_a)
        kwargs["dset_a"] = tablename_a

        dset_b = request.get_json().get('dset_b')
        if dset_b:
            dataset_object_b = DatasetService.get(dset_b)
            tablename_b =  '_'.join(dataset_object_b.get('tableName').split('/')) + '_processed'
            logging.debug(tablename_b)
            kwargs["dset_b"] = tablename_b

        date_a = request.get_json().get('date_a')
        logging.debug(f'date_a: {date_a}')
        kwargs["date_a"] = str(date_a)

        date_b = request.get_json().get('date_b')
        logging.debug(f'date_b: {date_b}')
        kwargs["date_b"] = str(date_b)

        lat = request.get_json().get('lat')
        logging.debug(f'lat: {lat}')
        kwargs["lat"] = str(lat)

        lon = request.get_json().get('lon')
        logging.debug(f'lon: {lon}')
        kwargs["lon"] = str(lon)

        varnames = request.get_json().get('varnames')
        logging.debug(f'varnames: {varnames}')
        kwargs["varnames"] = varnames

        return func(*args, **kwargs)
    return wrapper


def get_layer(func):
    """Get geodata"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logging.debug('Getting layer')
        layer = request.view_args.get('layer', None)
        logging.debug(f'layer: {layer}')
        try:
            layer_object = LayerService.get(layer)
        except LayerNotFound as e:
            return error(status=404, detail='Layer not found')
        logging.debug(f'layer_object: {layer_object}')
        kwargs["layer_object"] = layer_object
        return func(*args, **kwargs)
    return wrapper

def tile_exists(func):
    """Checks if the tile exists in the cache"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logging.info("[Middleware] Checking if tile exists in cache")
        logging.debug(f'request.path: {request.path}')
        request_id = request.path + '_' + str(kwargs['year'])
        logging.debug(request_id)
        url = RedisService.get(request_id)
        logging.debug(f'url: {url}')
        if url is None:
            logging.debug("No tile found in cache")
            return func(*args, **kwargs)
        else:
            logging.debug("Tile found, redirecting")
            return redirect(url)
    return wrapper

def is_microservice(func):
    """Get geodata"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logging.debug("Checking microservice user")
        logged_user = json.loads(request.args.get("loggedUser", None))
        if logged_user.get("id") == "microservice":
            logging.debug("is microservice");
            return func(*args, **kwargs)
        else:
            return error(status=403, detail="Not authorized")
    return wrapper
