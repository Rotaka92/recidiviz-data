class DataMigration(webapp2.RequestHandler):

    def get(self):
        """
        get()
        Request handler for data migration tasks. Migrates last_release_date 
        and last_release_type from UsNyRecord model to Record model, and old
        InmateFacilitySnapshot entities to new InmateSnapshot entities.

        Example queries:
        

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

        if rand_var != "898230981029381274897247":
            logging.error("Data migration request missing safeguard 'rand_var',"
                          " exiting.")
            self.response.write("Invalid parameters, see logs.")
            self.response.set_status(500)
            return

        test_only = True if test_only == "true" else False

        # Attempt migration
        snapshot_migration_complete = False
        record_migration_complete = False

        while not snapshot_migration_complete:
            snapshot_migration_complete = migrate_snapshots(test_only)

        while not record_migration_complete:
            record_migration_complete = migrate_record_fields(test_only)

        # Verify success / failure
        validate_snapshot_success()
        validate_record_success()

        # Unless test run, delete migrated InmateFacilitySnapshot records
        if not test_only:
            purge_migrated_snapshots()

        logging.info("Migration run complete.")


# TODO: Make transactional
def migrate_snapshots(test_only):
    """
    migrate_snapshots()
    Migrate InmateFacilitySnapshots into InmateSnapshot records. Reads in 50
    InmateFacilitySnapshots at a time, pulls the relevant fields from the
    corresponding UsNyRecord entities, and creates corresponding 50 
    InmateSnapshots. Updates the InmateFacilitySnapshots to migrated=True
    in the same transaction.

    Args:
        test_only: (bool) Whether this is a test migration (non-destructive, 
        fewer records) or not.

    Returns:
        True if completes migration of all InmateFacilitySnapshots
        False if not
    """
    entity_count = 5 if test_only else 50
    new_snapshot_entities = []
    migration_complete = False

    # Get (entity_count)x InmateFacilitySnapshots. If <50 returned, set 
    # migration_complete to True.

    # For each snapshot, pull date and facility info, parent record info, and
    # create new InmateSnapshot entity. Add to new_snapshot_entities.

    # Put new InmateSnapshot entities. If exceptions, return False.

    # Delete old InmateFacilitySnapshot entities
    if not test_only:
        pass

    return migration_complete


def migrate_record_fields(test_only):
    """
    """
    pass


def validate_snapshot_success(test_only):
    """
    """
    pass


def validate_record_success(test_only):
    """
    """
    pass

app = webapp2.WSGIApplication([
    ('/data_migration', DataMigration)
], debug=False)