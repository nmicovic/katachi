import logging
from pathlib import Path

from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode


def validate_schema(schema: SchemaNode, target_path: Path) -> bool:
    logging.debug(f"[schema_parse] <{schema.semantical_name}> @ {target_path}")
    if isinstance(schema, SchemaDirectory):
        # Perform basics checks for directory which are simple.
        # The real challenge is in validating children.

        # is it a dir?
        if not target_path.is_dir():
            logging.error(f"Validation failed! schema: {schema} : {target_path} is not a directory")
            return False

        # regexp pattern matching
        if schema.pattern_validation and not schema.pattern_validation.fullmatch(target_path.name):
            logging.error(f"Validation failed! schema: {schema} : {target_path} does not match pattern")
            return False

        child_paths = list(target_path.iterdir())
        logging.debug(f"[schema_parse] child_paths: {child_paths}")

        for child_path in child_paths:
            status = False

            # TODO other validations - probably pattern matching for name etc...
            for child in schema.children:
                if isinstance(child, SchemaFile):
                    status = _validate_file(child, child_path)
                else:
                    status = validate_schema(child, child_path)

            if not status:
                logging.error(f"Validation failed! schema: {schema} : {child} failed validation")
                return False

        return True
    elif isinstance(schema, SchemaFile):
        return _validate_file(schema, target_path)
    else:
        logging.error(f"Validation failed! schema: {schema} : Unknown schema type")
        return False


def _validate_file(schema: SchemaFile, file_path: Path) -> bool:
    logging.debug(f"[schema_parse] <{schema.semantical_name}> @ {file_path}")
    # is it a file?
    if not file_path.is_file():
        logging.error(f"Validation failed! schema: {schema} : {file_path} is not a file")
        return False

    # validate extension
    if schema.extension and file_path.suffix != schema.extension:
        logging.error(f"Validation failed! schema: {schema} : {file_path} has wrong extension")
        return False

    # regexp pattern matching
    if schema.pattern_validation and not schema.pattern_validation.fullmatch(file_path.stem):
        logging.error(f"Validation failed! schema: {schema} : {file_path} does not match pattern")
        return False

    return True
