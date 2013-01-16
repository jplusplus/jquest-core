from tastypie import fields
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from tastypie.authentication import BasicAuthentication
from tastypie.authorization import DjangoAuthorization
# Models available from the API
from django.contrib.auth.models import User
from jquest.models import *


class AdditionalModelResource(ModelResource):
    """ 
    Overrides the default ModelResource class to 
        - add an additional_detail_fields option that adds fields in detail mode
        - overrides the get_fields method to support the 'blank' attribute on model fields
    """

    class Meta:
        additional_detail_fields = {}

    # detail_dehydrate is basically full_dehydrate
    # except we'll loop over the additional_detail_fields
    # and we won't want to do the dehydrate(bundle) at the end
    def detail_dehydrate(self, bundle):
        """
        Given a bundle with an object instance, extract the information from it
        to populate the resource.
        """
        # Dehydrate each field.
        # loop over additional_detail_fields instead
        #for field_name, field_object in self.fields.items():
        for field_name, field_object in self._meta.additional_detail_fields.items():
            # A touch leaky but it makes URI resolution work.
            if getattr(field_object, 'dehydrated_type', None) == 'related':
                field_object.api_name = self._meta.api_name
                field_object.resource_name = self._meta.resource_name

            bundle.data[field_name] = field_object.dehydrate(bundle)

            # Check for an optional method to do further dehydration.
            method = getattr(self, "dehydrate_%s" % field_name, None)

            if method:
                bundle.data[field_name] = method(bundle)

        return bundle

    def dehydrate(self, bundle):
        # detect if detail
        if self.get_resource_uri(bundle) == bundle.request.path:
            # detail detected, include additional fields
            bundle = self.detail_dehydrate(bundle)
        return bundle

    @classmethod
    def get_fields(cls, fields=None, excludes=None):
        """
        Unfortunately we must override this method because tastypie ignores 'blank' attribute
        on model fields.

        Here we invoke an insane workaround hack due to metaclass inheritance issues:
            http://stackoverflow.com/questions/12757468/invoking-super-in-classmethod-called-from-metaclass-new
        """
        this_class = next(c for c in cls.__mro__ if c.__module__ == __name__ and c.__name__ == 'AdditionalModelResource')
        fields = super(this_class, cls).get_fields(fields=fields, excludes=excludes)
        if not cls._meta.object_class:
            return fields
        for django_field in cls._meta.object_class._meta.fields:
            if django_field.blank == True:
                res_field = fields.get(django_field.name, None)
                if res_field:
                    res_field.blank = True
        return fields

class UserResource(AdditionalModelResource):
    
    class Meta:
        excludes = ("password", "last_login", "email")
        queryset = User.objects.all()
        resource_name = 'user'
        always_return_data = True,
        filtering = {
            "date_joined": ALL,
            "first_name": ALL,
            "id": ALL,
            "is_active": ALL,
            "is_staff": ALL,
            "is_superuser": ALL,
            "last_name": ALL,            
            "resource_uri": ALL,
            "username": ALL,
        }

        additional_detail_fields = {
            'progressions': fields.ToManyField(
                'jquest.api.UserProgressionResource', 
                attribute=lambda bundle: UserProgression.objects.filter(user=bundle.obj),
                full=True, 
                null=True
            )
        }
        
        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()



    def obj_create(self, bundle, request=None, **kwargs):   
        """
            Overide the default obj_create method to save nested resources.
        """     
        bundle = super(UserResource, self).obj_create(bundle, request, **kwargs)      

        # Oauths insertion
        if 'oauths' in bundle.data:
            # The insertion mode is differents accoding the type of the oauths attribut
            oauth_type = type(bundle.data["oauths"])
            # Post request is asking for create several UserOauths at the same time
            if oauth_type == list:
                # For each given UserOauth object
                for o in bundle.data["oauths"]:
                    oauth = UserOauth(**o)
                    oauth.user = bundle.obj
                    oauth.save()        
            # Post request is asking for create an UserOauth at the same time
            elif oauth_type == dict:
                oauth = UserOauth(**bundle.data["oauths"])
                oauth.user = bundle.obj
                oauth.save()

        bundle.obj.save()
        return bundle


class UserProgressionResource(ModelResource):            
    mission = fields.ToOneField(
        "jquest.api.MissionResource",
        'mission',
        full=False
    )  
    class Meta:
        queryset = UserProgression.objects.all()
        resource_name = 'user_progression'
        always_return_data = True
        
        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()

        
    def dehydrate_state(self, bundle):                
        # Looks for the state display
        state = [state[1] for state in UserProgression.PROGRESSION_STATES if bundle.data["state"] == state[0]]
        return state[0] if len(state) > 0 else False


class UserOauthResource(ModelResource):
    user = fields.ToOneField(
        UserResource,
        "user",
        full=True
    )   
    class Meta:
        queryset = UserOauth.objects.all()
        resource_name = 'user_oauth'
        always_return_data = True
        filtering = {
            'consumer_user_id': ALL,
            'consumer': ALL,
            'user': ALL_WITH_RELATIONS
        }
        
        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()

class UserTokenResource(ModelResource):
    user = fields.ToOneField(
        UserResource,
        "user",
        full=True
    )   
    class Meta:
        queryset = UserToken.objects.all()
        resource_name = 'user_token'
        always_return_data = True
        filtering = {
            'user': ALL_WITH_RELATIONS,
            'token': ALL,
            'created_at': ALL
        }
        
        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()


class InstanceResource(AdditionalModelResource):  

    class Meta:    
        queryset = Instance.objects.all()
        additional_detail_fields = {
            'missions': fields.ToManyField(
                'jquest.api.MissionResource', 
                attribute=lambda bundle: Mission.objects.filter(instance=bundle.obj),
                full=True, 
                null=True
            )
        }
        resource_name = 'instance'
        always_return_data = True
        filtering = {
            'slug': ALL,
            'name': ALL,
            'host': ALL,
            'missions__id': ALL
        }
        
        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()


class MissionResource(ModelResource):
    # Instance related to that mission
    instance = fields.ToOneField(
        InstanceResource,
        'instance',
        full=False
    )    

    # parent
    relationships = fields.ToManyField(
        "jquest.api.MissionRelationshipResource",
        attribute=lambda bundle: MissionRelationship.objects.filter(mission=bundle.obj),        
        full=True, 
        null=True
    )

    """
        # All users progressions related to that mission
        progressions = fields.ToManyField(
            to="jquest.api.UserProgressionResource",
            attribute=lambda bundle: UserProgression.objects.filter(mission=bundle.obj), 
            full=True,
            null=True        
        ) 
    """

    class Meta:
        queryset = Mission.objects.all()
        resource_name = 'mission'
        always_return_data = True
        excludes = ("progressions",)
        filtering = {
            'name': ALL,
            'instance': ALL
        }        

        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()

    # Convert image path to an URL
    def dehydrate_image(self, bundle):
        return bundle.request.build_absolute_uri(bundle.data["image"]) if bundle.data["image"] else None 


class MissionRelationshipResource(ModelResource):
    parent  = fields.ToOneField(MissionResource, "parent", full=False)
    mission = fields.ToOneField(MissionResource, "mission", full=False)

    class Meta:
        queryset = MissionRelationship.objects.all()
        resource_name = 'mission_relationship'
        
        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()



class LanguageResource(ModelResource):
    class Meta:
        queryset = Language.objects.all()
        resource_name = 'language'
        always_return_data = True
        
        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()

class PostResource(ModelResource):
    class Meta:
        queryset = Post.objects.all()
        resource_name = 'post'
        always_return_data = True
        
        authentication = BasicAuthentication()
        authorization = DjangoAuthorization()