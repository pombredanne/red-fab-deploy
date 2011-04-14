#''' Store server information in SimpleDB, Notify on changes '''
#
#from fab_deploy.aws import *
#import boto.sns
#
#domain_name = 'servers'
#
#def create_domain():
#    conn = boto.SimpleDbConnection(**aws_connection_opts())
#    domain = conn.get_domain(domain_name) or conn.create_domain(domain_name)
#    
#def create(name, **kwargs):
#    item = domain.new_item(name)
#    for k, v in kwargs.iteritems():
#        item[k] = v
#    item.save()
#    
#def filter(**kwargs):
#    return domain.select("SELECT * FROM `%s` WHERE %s" % (domain_name, " AND ".join("`%s` = '%s'" % (k,v) for k,v in kwargs.iteritems())))

from fab_deploy.aws import *
import boto.sns

topic_name = 'database_servers_updated'

def create_topic():
    conn = boto.sns.SNSConnection(**aws_connection_opts())
    conn.create_topic(topic_name)
    
