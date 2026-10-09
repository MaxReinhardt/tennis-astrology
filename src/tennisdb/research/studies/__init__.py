"""Study registry — the composition root for research studies. Adding a study means
adding one entry to STUDIES; scripts/run_study.py and the web API both read it."""

from tennisdb.research.protocol import Study
from tennisdb.research.studies.s1_clv_persistence import ClvPersistenceStudy
from tennisdb.research.studies.s2_favourite_longshot import FavouriteLongshotStudy
from tennisdb.research.studies.s3_zodiac_null import ZodiacNullStudy
from tennisdb.research.studies.s4_host_nation import HostNationStudy

STUDIES: dict[str, Study] = {
    study.study_id: study
    for study in (
        ClvPersistenceStudy(),
        FavouriteLongshotStudy(),
        ZodiacNullStudy(),
        HostNationStudy(),
    )
}
