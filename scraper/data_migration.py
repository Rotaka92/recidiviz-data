import logging

from google.appengine.ext import deferred
from google.appengine.ext import ndb
from us_ny.us_ny_inmate_snapshot import UsNyInmateSnapshot
from us_ny.us_ny_inmate import UsNyInmate
from us_ny.us_ny_record import UsNyRecord
from models.inmate_snapshot import InmateFacilitySnapshot
import webapp2


TEST_BATCH_SIZE = 10

class DataMigration(webapp2.RequestHandler):

    def get(self):
        """
        get()
        Request handler for data migration tasks. Migrates last_release_date 
        and last_release_type from UsNyRecord model to Record model, and old
        InmateFacilitySnapshot entities to new InmateSnapshot entities.

        Example queries:
        # Migrate 5x snapshots only.
        http://localhost:8080/data_migration?rand_var=898230981029381274897247&test_only=true&migration_type=snapshot

        # Migrate 5x Record entities only
        http://localhost:8080/data_migration?rand_var=898230981029381274897247&test_only=true&migration_type=record

        # Migrate all snapshots
        http://localhost:8080/data_migration?rand_var=898230981029381274897247&test_only=false&migration_type=snapshot

        # Migrate all records
        http://localhost:8080/data_migration?rand_var=898230981029381274897247&test_only=false&migration_type=record

        Args:
            rand_var: Must == 898230981029381274897247, just in case does hit prod
            env_only: "true" or "false", whether to populate only the environment
                      variables (no fake data)

        Returns:
            HTTP 200 if successful 
            HTTP 400 if not
        """
        # Get and validate params
        rand_var = self.request.get('rand_var', None)
        test_only = self.request.get('test_only', "true").lower()
        migration_type = self.request.get('migration_type', "snapshot").lower()

        test_only = True if test_only == "true" else False

        if rand_var != "898230981029381274897247":
            logging.error("Data migration request missing safeguard 'rand_var',"
                          " exiting.")
            self.response.write("Invalid parameters, see logs.")
            self.response.set_status(500)
            return

        if migration_type == "snapshot":
            if test_only:
                migrate_snapshots(batch_size=TEST_BATCH_SIZE)
            else:
                deferred.defer(migrate_snapshots)
        elif migration_type == "record":
            if test_only:
                migrate_record_fields(batch_size=TEST_BATCH_SIZE)
            else:
                deferred.defer(migrate_record_fields)
        else:
            logging.error("Migration type '%s' not recognized. Exiting." % 
                migration_type)
            self.response.write("Invalid parameters, see logs.")
            self.response.set_status(500)
            return

        self.response.write("Kicked off migration.")
        logging.info("Kicked off migration.")


def migrate_snapshots(cursor=None, num_updated=0, batch_size=100):
    """
    migrate_snapshots()
    Migrate InmateFacilitySnapshots into InmateSnapshot records. Reads in 50
    InmateFacilitySnapshots at a time, pulls the relevant fields from the
    corresponding UsNyRecord entities, and creates corresponding 50 
    InmateSnapshots. Updates the InmateFacilitySnapshots to migrated=True
    in the same transaction.

    Args:
        cursor: Query cursor for where we are in the migration
        num_updated: Current number of records updated
        batch_size: Number of records to handle during this run

    Returns:
        True if completes migration of all InmateFacilitySnapshots
    """
    # Get (entity_count)x InmateFacilitySnapshots. If <50 returned, set 
    # migration_complete to True.
    inmate_facility_query = InmateFacilitySnapshot.query()
    inmate_facility_snapshots, next_cursor, more = inmate_facility_query.fetch_page(
        batch_size, start_cursor=cursor)

    to_put = []
    to_del = []

    # For each snapshot, pull date and facility info, parent record info, and
    # create new InmateSnapshot entity. Add to new_snapshot_entities.
    for facility_snapshot in inmate_facility_snapshots:
        record_key = facility_snapshot.key.parent()
        record = record_key.get()

        inmate_snapshot = UsNyInmateSnapshot(parent=record_key,
                                             snapshot_date=facility_snapshot.snapshot_date,
                                             facility=facility_snapshot.facility,
                                             last_release_date=record.last_release_date,
                                             last_release_type=record.last_release_type,
                                             is_released=record.is_released,
                                             min_sentence_length=record.min_sentence_length,
                                             max_sentence_length=record.max_sentence_length,
                                             last_custody_date=record.last_custody_date,
                                             admission_type=record.admission_type,
                                             county_of_commit=record.county_of_commit,
                                             custody_status=record.custody_status,
                                             earliest_release_date=record.earliest_release_date,
                                             earliest_release_type=record.earliest_release_type,
                                             parole_hearing_date=record.parole_hearing_date,
                                             parole_hearing_type=record.parole_hearing_type,
                                             parole_elig_date=record.parole_elig_date,
                                             cond_release_date=record.cond_release_date,
                                             max_expir_date=record.max_expir_date,
                                             max_expir_date_superv=record.max_expir_date_superv,
                                             max_expir_date_parole=record.max_expir_date_parole,
                                             parole_discharge_date=record.parole_discharge_date)

        to_put.append(inmate_snapshot)
        to_del.append(facility_snapshot.key)

    # Save the updated entities.
    if to_put:
        ndb.put_multi(to_put)
        num_updated += len(to_put)
        logging.info('Put %d updated snapshot entities for a total of %s' %
                     (len(to_put), num_updated))

    # Delete migrated snapshots
    if to_del:
        ndb.delete_multi(to_del)

    # If there are more entities, re-queue this task for the next page.
    if more:
        deferred.defer(
            migrate_snapshots, cursor=next_cursor, num_updated=num_updated)
    else:
        logging.debug(
            'migrate_snapshots complete with %d updates!' % num_updated)


def migrate_record_fields(cursor=None, num_updated=0, batch_size=100):
    """
    migrate_record_fields
    Transfers the UsNyRecord fields 'last_release_date' and 'last_release_type'
    to Record superclass as 'latest_release_date' and 'latest_release_type'. 
    Name change is to avoid DuplicatePropertyError from Polymodel class.

    Args:
        cursor: Query cursor for where we are in the migration
        num_updated: Current number of records updated
        batch_size: Number of records to handle during this run

    Returns
        Nothing
    """
    record_query = UsNyRecord.query()
    records, next_cursor, more = record_query.fetch_page(
        batch_size, start_cursor=cursor)

    to_put = []

    for record in records:
        # Move properties to new, superclass-level properties
        # 'if...' checks protect against any accidental re-running of the migration
        if not hasattr(record, 'latest_release_date') or not record.latest_release_date:
            record.latest_release_date = record.last_release_date

        if not hasattr(record, 'latest_release_type') or not record.latest_release_type:
            record.latest_release_type = record.last_release_type

        # Clone properties to the instance (so as not to delete from the class),
        # and delete from the entity.
        record._clone_properties()
        del record._properties['last_release_type']
        del record._properties['last_release_date']

        to_put.append(record)
        
    # Save the updated entities.
    if to_put:
        ndb.put_multi(to_put)
        num_updated += len(to_put)
        logging.info('Put %d updated record entities for a total of %s' %
                     (len(to_put), num_updated))

    # If there are more entities, re-queue this task for the next page.
    if more:
        deferred.defer(
            migrate_record_fields, cursor=next_cursor, num_updated=num_updated)
    else:
        logging.debug(
            'migrate_record_fields complete with %d updates!' % num_updated)


app = webapp2.WSGIApplication([
    ('/data_migration', DataMigration)
], debug=False)