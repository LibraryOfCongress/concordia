import os
from logging import getLogger
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render_to_response,render, redirect
from registration.backends.simple.views import RegistrationView
from .forms import ConcordiaUserForm, ConcordiaUserEditForm
from .models import UserProfile
from transcribr.transcribr.models import Asset, Collection, Transcription, UserAssetTagCollection, Tag
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from importer.importer.tasks import download_async_collection, check_completeness
from config import config

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36

def transcribr_api(relative_path):
    abs_path = '{}/api/v1/{}'.format(
        settings.TRANSCRIBR['netloc'],
        relative_path
    )
    logger.debug('Calling API path {}'.format(abs_path))
    data = requests.get(abs_path).json()

    logger.debug('Received {}'.format(data))
    return data


class ConcordiaRegistrationView(RegistrationView):
    form_class = ConcordiaUserForm


class AccountProfileView(LoginRequiredMixin, TemplateView):

    
    template_name = 'profile.html'
    
    def post(self, *args, **kwargs):
        context = self.get_context_data()
        instance = get_object_or_404(User, pk=self.request.user.id)
        form = ConcordiaUserEditForm(self.request.POST, self.request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save(commit=True)
            obj.id = self.request.user.id
            if not self.request.POST['password1'] and not self.request.POST['password2']:
              obj.password=self.request.user.password
            obj.save()
            if 'myfile' in self.request.FILES:
              myfile = self.request.FILES['myfile']
              profile, created = UserProfile.objects.update_or_create(user=obj, defaults={'myfile':myfile})
        return redirect(reverse('user-profile'))

    def get_context_data(self, **kws):
        last_name = self.request.user.last_name
        if last_name:
            last_name = " " + last_name
        else:
            last_name=''
            
        data = {'username': self.request.user.username, 'email':self.request.user.email, 'first_name':self.request.user.first_name + last_name}
        profile = UserProfile.objects.filter(user=self.request.user)
        if profile:
            data['myfile'] = profile[0].myfile
        return super().get_context_data(**dict(
            kws,
            transcriptions=Transcription.objects.filter(user_id=self.request.user.id).order_by('-updated_on'),
            
            form = ConcordiaUserEditForm(initial=data)
        ))

class TranscribrView(TemplateView):
    template_name = 'transcriptions/home.html'

    def get_context_data(self, **kws):
        response = transcribr_api('collections/')
        return dict(
            super().get_context_data(**kws),
            response=response
        )


class TranscribrCollectionView(TemplateView):
    template_name = 'transcriptions/collection.html'

    def get_context_data(self, **kws):
        collection = Collection.objects.get(slug=self.args[0])
        asset_list = collection.asset_set.all()
        paginator = Paginator(asset_list, ASSETS_PER_PAGE)

        if not self.request.GET.get('page'):
            page = 1
        else:
            page = self.request.GET.get('page')

        assets = paginator.get_page(page)

        return dict(
            super().get_context_data(**kws),
            collection=collection,
            assets=assets
        )


class TranscribrAssetView(TemplateView):
    template_name = 'transcriptions/asset.html'

    def get_context_data(self, **kws):
   
        asset = Asset.objects.get(collection__slug=self.args[0], slug=self.args[1])
        
        transcription = Transcription.objects.filter(asset=asset, user_id=self.request.user.id)
        if transcription:
          transcription = transcription[0]
        tags = UserAssetTagCollection.objects.filter(asset=asset, user_id=self.request.user.id)
        if tags:
          tags = tags[0].tags.all() 

        return dict(
            super().get_context_data(**kws),
            asset=asset,
            transcription=transcription,
            tags=tags
        )

    def post(self, *args, **kwargs):
        context = self.get_context_data()
        asset = Asset.objects.get(collection__slug=self.args[0], slug=self.args[1])
        if 'tx' in self.request.POST:
          tx = self.request.POST.get('tx')
          status = self.request.POST.get('status', '25')
          Transcription.objects.update_or_create(asset=asset,
                                                 user_id=self.request.user.id,
                                                 defaults={'text':tx, 'status':status})
        if 'tags' in self.request.POST:
          tags = self.request.POST.get('tags').split(',')
          utags, status = UserAssetTagCollection.objects.get_or_create(asset=asset, user_id=self.request.user.id)
          all_tag = utags.tags.all().values_list('name', flat=True)
          all_tag_list = list(all_tag)
          delete_tags = [i for i in all_tag_list if i not in tags]
          utags.tags.filter(name__in = delete_tags).delete()
          for tag in tags:
            tag_ob, t_status = Tag.objects.get_or_create(name=tag, value=tag)
            if tag_ob not in utags.tags.all():
              utags.tags.add(tag_ob)
          
        return redirect(self.request.path)


class TranscriptionView(TemplateView):
    template_name = 'transcriptions/transcription.html'

    def get_context_data(self, **kws):
        transcription = Transcription.objects.get(id=self.args[0])
        transcription_user = get_user_model().objects.get(id=transcription.id)
        return super().get_context_data(**dict(
            kws,
            transcription=transcription,
            transcription_user=transcription_user
        ))


class ToDoView(TemplateView):
    template_name = 'todo.html'


class ExperimentsView(TemplateView):

    def get_template_names(self):
        return ['experiments/{}.html'.format(self.args[0])]
        
class CollectionView(TemplateView):
    template_name = 'transcriptions/create.html'
    
    def post(self, *args, **kwargs):
        context = self.get_context_data()
        name = self.request.POST.get('name')
        url = self.request.POST.get('url')
        #c = Collection.objects.create(title=name, slug=name.replace(" ","-"), description=name)
        
        result = download_async_collection.delay("https://www.loc.gov/collections/clara-barton-papers/?fa=partof:clara+barton+papers:++diaries+and+journals,+1849-1911")
        result.ready()
        result.get()
        result2 = check_completeness.delay()
        try:
          result2.ready()
          result2.get()
        except Exception as e:
            pass
            
        print ("lakshman---testfffff", result2.state)
        if not result2.state == 'PENDING':
          base_dir = config('IMPORTER', 'IMAGES_FOLDER')
          base_dir = settings.BASE_DIR if not base_dir else base_dir 
          print ("base_dir", base_dir)
          collection_path  = settings.MEDIA_ROOT+"/"+name.replace(' ', '-')
          os.makedirs(collection_path)
          cmd = 'mv {0}/mss* {1}'.format(base_dir, collection_path)
          os.system(cmd)
          '''
          for root, dirs, files in os.walk(base_dir): 
            for filename in files:
              filename = os.path.join(root, filename)
              if "mss1197300" in filename:
                print("dirs", os.path.join(dirs, filename))
                print(os.path.join(root, filename))
                collection_path  = settings.MEDIA_ROOT+"/"+name
                os.makedirs(collection_path)
                dest = filename.replace(base_dir, collection_path)
                print ("dest", dest)
                
                import shutil
                import pdb; pdb.set_trace()
                shutil.move(filename, dest)
                break
          '''
            
        
        return redirect(self.request.path)
        

    
